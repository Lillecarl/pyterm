//! A window's frames as kitty graphics protocol commands.
//!
//! The first frame, and the first after a resize, goes over whole
//! (`a=t`). After that only the damaged rectangles go, as edits of the
//! image's root frame (`a=f,r=1,X=1`): kitty composes an edit into the
//! frame it holds and redraws it in place (`graphics.c`,
//! `handle_animation_frame_load_command`, the "existing frame" arm).

use std::io::Write;

use base64::Engine;
use base64::engine::general_purpose::STANDARD;
use flate2::Compression;
use flate2::write::ZlibEncoder;

use crate::Rect;

/// kitty takes at most this many bytes of base64 in one command.
const CHUNK: usize = 4096;

/// Past this many rectangles, or this share of the frame, one bounding
/// box costs less than the edits: each edit is a command of its own.
const MOST_RECTANGLES: usize = 16;
const MOST_SHARE: f64 = 0.5;

/// The pixels of one frame: RGBA rows, `stride` bytes apart.
pub struct Pixels<'a> {
    pub width: i32,
    pub height: i32,
    pub stride: usize,
    pub rgba: &'a [u8],
    /// No pixel is translucent, so three bytes a pixel carry it.
    pub opaque: bool,
}

impl Pixels<'_> {
    /// A copy that owns its bytes, to encode on another thread.
    pub fn to_owned(&self) -> OwnedPixels {
        OwnedPixels {
            width: self.width,
            height: self.height,
            stride: self.stride,
            rgba: self.rgba.to_vec(),
            opaque: self.opaque,
        }
    }
}

/// `Pixels` that own their bytes.
pub struct OwnedPixels {
    width: i32,
    height: i32,
    stride: usize,
    rgba: Vec<u8>,
    opaque: bool,
}

impl OwnedPixels {
    pub fn view(&self) -> Pixels<'_> {
        Pixels {
            width: self.width,
            height: self.height,
            stride: self.stride,
            rgba: &self.rgba,
            opaque: self.opaque,
        }
    }
}

/// The commands that send the whole frame under `image_id`.
pub fn transmit(pixels: &Pixels, image_id: u32) -> String {
    let rect = (0, 0, pixels.width, pixels.height);
    let keys = format!(
        "a=t,i={image_id},s={},v={},q=2",
        pixels.width, pixels.height
    );
    encode(pixels, rect, &keys)
}

/// The commands that bring `image_id` up to date, given the rectangles
/// damaged since the frame the terminal holds.
pub fn edit(pixels: &Pixels, image_id: u32, damage: &[Rect]) -> String {
    let mut out = String::new();
    for rect in coalesced(damage, pixels.width, pixels.height) {
        let (x, y, w, h) = rect;
        let keys = format!("a=f,i={image_id},r=1,x={x},y={y},s={w},v={h},X=1,q=2");
        out.push_str(&encode(pixels, rect, &keys));
    }
    out
}

/// The rectangles to send: as given, or their bounding box when that is
/// cheaper.
fn coalesced(damage: &[Rect], width: i32, height: i32) -> Vec<Rect> {
    let area: i64 = damage
        .iter()
        .map(|&(_, _, w, h)| i64::from(w) * i64::from(h))
        .sum();
    let whole = i64::from(width) * i64::from(height);
    if damage.len() <= MOST_RECTANGLES && (area as f64) < MOST_SHARE * whole as f64 {
        return damage.to_vec();
    }
    let left = damage.iter().map(|r| r.0).min().unwrap_or(0);
    let top = damage.iter().map(|r| r.1).min().unwrap_or(0);
    let right = damage.iter().map(|r| r.0 + r.2).max().unwrap_or(0);
    let bottom = damage.iter().map(|r| r.1 + r.3).max().unwrap_or(0);
    vec![(left, top, right - left, bottom - top)]
}

/// The rectangles a reader needs, each with its pixels as kitty's `f=24`
/// (RGB) or `f=32` (RGBA) reads them: the whole frame, or the damage
/// coalesced as `edit` sends it.
pub fn rects(pixels: &Pixels, damage: Option<&[Rect]>) -> Vec<(Rect, Vec<u8>)> {
    let rects = match damage {
        Some(damage) => coalesced(damage, pixels.width, pixels.height),
        None => vec![(0, 0, pixels.width, pixels.height)],
    };
    rects
        .into_iter()
        .map(|rect| (rect, raw(pixels, rect)))
        .collect()
}

fn raw(pixels: &Pixels, (x, y, w, h): Rect) -> Vec<u8> {
    let size = if pixels.opaque { 3 } else { 4 };
    let mut raw = Vec::with_capacity(w as usize * h as usize * size);
    for row in y..y + h {
        let start = row as usize * pixels.stride + x as usize * 4;
        let line = &pixels.rgba[start..start + w as usize * 4];
        if pixels.opaque {
            for pixel in line.chunks_exact(4) {
                raw.extend_from_slice(&pixel[..3]);
            }
        } else {
            raw.extend_from_slice(line);
        }
    }
    raw
}

/// One rectangle of the frame, compressed and chunked behind `keys`.
fn encode(pixels: &Pixels, rect: Rect, keys: &str) -> String {
    let format = if pixels.opaque { 24 } else { 32 };
    let raw = raw(pixels, rect);

    let mut encoder = ZlibEncoder::new(Vec::new(), Compression::fast());
    // A Vec takes every write.
    encoder.write_all(&raw).expect("writing to a Vec");
    let payload = STANDARD.encode(encoder.finish().expect("writing to a Vec"));

    let chunks: Vec<&str> = if payload.is_empty() {
        vec![""]
    } else {
        payload
            .as_bytes()
            .chunks(CHUNK)
            .map(|chunk| std::str::from_utf8(chunk).expect("base64 is ASCII"))
            .collect()
    };
    let mut out = String::with_capacity(payload.len() + chunks.len() * 32 + keys.len());
    for (index, chunk) in chunks.iter().enumerate() {
        let more = u8::from(index + 1 < chunks.len());
        if index == 0 {
            out.push_str(&format!(
                "\x1b_G{keys},f={format},o=z,m={more};{chunk}\x1b\\"
            ));
        } else {
            out.push_str(&format!("\x1b_Gm={more};{chunk}\x1b\\"));
        }
    }
    out
}
