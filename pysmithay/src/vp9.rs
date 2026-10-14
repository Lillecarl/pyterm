//! A window's frames as a VP9 stream, for a reader on a link too narrow
//! for raw pixels. libvpx encodes 4:4:4, tuned for screen content, and
//! only the 16x16 blocks under the damage: the rest of the frame goes as
//! "unchanged" (libvpx's active map), which costs neither time nor bytes.
//! pymux_rs decodes it on the client. Lillecarl/pymux#639.

use std::ffi::CStr;
use std::sync::Mutex;

use pyo3::prelude::*;

use crate::Rect;
use crate::kitty::{Pixels, coalesced};

#[allow(
    non_upper_case_globals,
    non_camel_case_types,
    non_snake_case,
    dead_code,
    unused_imports,
    unsafe_op_in_unsafe_fn,
    clippy::all
)]
mod ffi {
    include!(concat!(env!("OUT_DIR"), "/vpx.rs"));
}

/// The side of the blocks the active map marks.
const BLOCK: i32 = 16;

/// libvpx's constant quality level, 0 to 63. At 24, Firefox scrolling
/// measured 29 KB a frame at 45 dB, against 89 KB at 43 dB for x264.
const QUALITY: i32 = 24;

/// `cpu-used`: the fastest realtime setting.
const SPEED: i32 = 8;

/// Two to the power of this many tile columns, which threads encode
/// side by side.
const TILE_COLUMNS: i32 = 2;

/// What one call of `encode` answers: whether the frame is a keyframe,
/// the data, and the block-aligned rectangles that changed.
pub type Encoded = (bool, Vec<u8>, Vec<Rect>);

struct Context(ffi::vpx_codec_ctx_t);

// SAFETY: libvpx keeps no thread-local state for a context; the Mutex
// in `Vp9Encoder` lets one thread at a time use it.
unsafe impl Send for Context {}

impl Context {
    fn error(&self) -> String {
        // SAFETY: libvpx answers a static string for any context.
        unsafe { CStr::from_ptr(ffi::vpx_codec_error(&self.0)) }
            .to_string_lossy()
            .into_owned()
    }

    fn control(&mut self, id: u32, value: i32) -> Result<(), String> {
        // SAFETY: every control `Stream::new` sets takes an int.
        let status = unsafe { ffi::vpx_codec_control_(&mut self.0, id as i32, value) };
        self.check(status)
    }

    fn check(&self, status: ffi::vpx_codec_err_t) -> Result<(), String> {
        if status == ffi::vpx_codec_err_t_VPX_CODEC_OK {
            Ok(())
        } else {
            Err(self.error())
        }
    }
}

impl Drop for Context {
    fn drop(&mut self) {
        // SAFETY: the context was initialised by `Stream::new`, and dies once.
        unsafe { ffi::vpx_codec_destroy(&mut self.0) };
    }
}

/// One stream at one size: the encoder, the frame it last took as Y, U
/// and V planes, and the serial of the window frame that was.
struct Stream {
    context: Context,
    width: i32,
    height: i32,
    planes: Vec<u8>,
    /// Frames encoded, as libvpx's timestamps.
    count: i64,
    serial: u64,
}

impl Stream {
    fn new(width: i32, height: i32) -> Result<Self, String> {
        // SAFETY: libvpx fills the whole config.
        let mut config: ffi::vpx_codec_enc_cfg_t = unsafe { std::mem::zeroed() };
        // SAFETY: `config` outlives the call.
        let status =
            unsafe { ffi::vpx_codec_enc_config_default(ffi::vpx_codec_vp9_cx(), &mut config, 0) };
        if status != ffi::vpx_codec_err_t_VPX_CODEC_OK {
            return Err("libvpx has no VP9 encoder".into());
        }
        // Profile 1 is 4:4:4: 4:2:0 halves the colour, which smears
        // coloured text.
        config.g_profile = 1;
        config.g_w = width as u32;
        config.g_h = height as u32;
        config.g_timebase = ffi::vpx_rational { num: 1, den: 30 };
        config.g_lag_in_frames = 0;
        config.g_threads =
            std::thread::available_parallelism().map_or(1, |cores| cores.get().min(8)) as u32;
        config.rc_end_usage = ffi::vpx_rc_mode_VPX_Q;
        config.kf_mode = ffi::vpx_kf_mode_VPX_KF_DISABLED;
        // SAFETY: an all-zero context is what `vpx_codec_enc_init` expects.
        let mut context = Context(unsafe { std::mem::zeroed() });
        // SAFETY: `context` and `config` outlive the call.
        let status = unsafe {
            ffi::vpx_codec_enc_init_ver(
                &mut context.0,
                ffi::vpx_codec_vp9_cx(),
                &config,
                0,
                ffi::VPX_ENCODER_ABI_VERSION as i32,
            )
        };
        if status != ffi::vpx_codec_err_t_VPX_CODEC_OK {
            // A failed init leaves nothing to destroy.
            let message = context.error();
            std::mem::forget(context);
            return Err(message);
        }
        context.control(ffi::vp8e_enc_control_id_VP8E_SET_CPUUSED, SPEED)?;
        context.control(ffi::vp8e_enc_control_id_VP8E_SET_CQ_LEVEL, QUALITY)?;
        context.control(ffi::vp8e_enc_control_id_VP9E_SET_ROW_MT, 1)?;
        context.control(ffi::vp8e_enc_control_id_VP9E_SET_TILE_COLUMNS, TILE_COLUMNS)?;
        context.control(
            ffi::vp8e_enc_control_id_VP9E_SET_TUNE_CONTENT,
            ffi::vp9e_tune_content_VP9E_CONTENT_SCREEN as i32,
        )?;
        context.control(ffi::vp8e_enc_control_id_VP9E_SET_COLOR_RANGE, 1)?;
        context.control(
            ffi::vp8e_enc_control_id_VP9E_SET_COLOR_SPACE,
            ffi::vpx_color_space_VPX_CS_BT_601 as i32,
        )?;
        Ok(Self {
            context,
            width,
            height,
            planes: vec![0; 3 * width as usize * height as usize],
            count: 0,
            serial: 0,
        })
    }

    /// Bring the planes under `rect` up to date with `pixels`.
    fn take(&mut self, pixels: &Pixels, (x, y, w, h): Rect) {
        let area = self.width as usize * self.height as usize;
        let (luma, chroma) = self.planes.split_at_mut(area);
        let (u_plane, v_plane) = chroma.split_at_mut(area);
        for row in y as usize..(y + h) as usize {
            let source = &pixels.rgba[row * pixels.stride..];
            for column in x as usize..(x + w) as usize {
                let pixel = &source[column * 4..column * 4 + 3];
                let (y, u, v) = rgb_to_yuv(pixel[0], pixel[1], pixel[2]);
                let at = row * self.width as usize + column;
                luma[at] = y;
                u_plane[at] = u;
                v_plane[at] = v;
            }
        }
    }

    fn encode(&mut self, rects: Option<&[Rect]>) -> Result<Vec<u8>, String> {
        let mut map = rects.map(|rects| active_map(rects, self.width, self.height));
        let (columns, rows) = (blocks(self.width), blocks(self.height));
        let mut active = ffi::vpx_active_map_t {
            active_map: map
                .as_mut()
                .map_or(std::ptr::null_mut(), |map| map.as_mut_ptr()),
            rows: rows as u32,
            cols: columns as u32,
        };
        // SAFETY: `active` and its map outlive the call, which copies it.
        let status = unsafe {
            ffi::vpx_codec_control_(
                &mut self.context.0,
                ffi::vp8e_enc_control_id_VP8E_SET_ACTIVEMAP as i32,
                &mut active as *mut ffi::vpx_active_map_t,
            )
        };
        self.context.check(status)?;

        // SAFETY: an all-zero image is what `vpx_img_wrap` fills.
        let mut image: ffi::vpx_image_t = unsafe { std::mem::zeroed() };
        // SAFETY: the planes outlive the encode, and hold three planes of
        // `width` by `height` bytes, one after the other.
        unsafe {
            ffi::vpx_img_wrap(
                &mut image,
                ffi::vpx_img_fmt_VPX_IMG_FMT_I444,
                self.width as u32,
                self.height as u32,
                1,
                self.planes.as_mut_ptr(),
            )
        };
        image.range = ffi::vpx_color_range_VPX_CR_FULL_RANGE;
        image.cs = ffi::vpx_color_space_VPX_CS_BT_601;
        let flags = if rects.is_none() {
            ffi::VPX_EFLAG_FORCE_KF as ffi::vpx_enc_frame_flags_t
        } else {
            0
        };
        // SAFETY: `image` and its planes outlive the call.
        let status = unsafe {
            ffi::vpx_codec_encode(
                &mut self.context.0,
                &image,
                self.count,
                1,
                flags,
                ffi::VPX_DL_REALTIME as std::os::raw::c_ulong,
            )
        };
        self.context.check(status)?;
        self.count += 1;

        let mut data = Vec::new();
        let mut iterator: ffi::vpx_codec_iter_t = std::ptr::null();
        // SAFETY: a packet lives until the next call into the context.
        while let Some(packet) =
            unsafe { ffi::vpx_codec_get_cx_data(&mut self.context.0, &mut iterator).as_ref() }
        {
            if packet.kind == ffi::vpx_codec_cx_pkt_kind_VPX_CODEC_CX_FRAME_PKT {
                // SAFETY: a frame packet holds `sz` bytes at `buf`.
                let frame = unsafe { packet.data.frame };
                data.extend_from_slice(unsafe {
                    std::slice::from_raw_parts(frame.buf.cast::<u8>(), frame.sz)
                });
            }
        }
        Ok(data)
    }
}

fn blocks(pixels: i32) -> i32 {
    (pixels + BLOCK - 1) / BLOCK
}

/// The damage grown out to whole blocks, cut to the frame, and merged as
/// the kitty edits merge it.
fn block_rects(damage: &[Rect], width: i32, height: i32) -> Vec<Rect> {
    let grown: Vec<Rect> = damage
        .iter()
        .map(|&(x, y, w, h)| {
            let (left, top) = (x / BLOCK * BLOCK, y / BLOCK * BLOCK);
            let right = (blocks(x + w) * BLOCK).min(width);
            let bottom = (blocks(y + h) * BLOCK).min(height);
            (left, top, right - left, bottom - top)
        })
        .filter(|&(_, _, w, h)| w > 0 && h > 0)
        .collect();
    coalesced(&grown, width, height)
}

/// One byte a block, 1 where a rectangle covers it.
fn active_map(rects: &[Rect], width: i32, height: i32) -> Vec<u8> {
    let columns = blocks(width);
    let mut map = vec![0u8; (columns * blocks(height)) as usize];
    for &(x, y, w, h) in rects {
        for row in y / BLOCK..blocks(y + h) {
            for column in x / BLOCK..blocks(x + w) {
                map[(row * columns + column) as usize] = 1;
            }
        }
    }
    map
}

/// Full range BT.601, in 1/65536ths: what pymux_rs's decoder inverts.
fn rgb_to_yuv(r: u8, g: u8, b: u8) -> (u8, u8, u8) {
    let (r, g, b) = (i32::from(r), i32::from(g), i32::from(b));
    let y = (19595 * r + 38470 * g + 7471 * b + 32768) >> 16;
    let u = ((-11059 * r - 21709 * g + 32768 * b + 32768) >> 16) + 128;
    let v = ((32768 * r - 27439 * g - 5329 * b + 32768) >> 16) + 128;
    (
        y.clamp(0, 255) as u8,
        u.clamp(0, 255) as u8,
        v.clamp(0, 255) as u8,
    )
}

/// One reader's VP9 stream of one window. A stream holds the frames it
/// sent as its reference, so every reader has an encoder of its own.
#[pyclass(name = "Vp9Encoder", frozen)]
#[derive(Default)]
pub struct Vp9Encoder {
    stream: Mutex<Option<Stream>>,
}

#[pymethods]
impl Vp9Encoder {
    #[new]
    fn new() -> Self {
        Self::default()
    }
}

impl Vp9Encoder {
    /// The size and serial of the last frame encoded, or None before
    /// the first.
    pub fn last(&self) -> Option<(i32, i32, u64)> {
        let stream = self
            .stream
            .lock()
            .unwrap_or_else(|poisoned| poisoned.into_inner());
        stream
            .as_ref()
            .map(|stream| (stream.width, stream.height, stream.serial))
    }

    /// Encode window frame `serial`, given the damage since the last
    /// frame this encoder took, or None to start again with a keyframe.
    /// A new size starts again too.
    pub fn encode(
        &self,
        pixels: &Pixels,
        serial: u64,
        damage: Option<&[Rect]>,
    ) -> Result<Encoded, String> {
        let mut held = self
            .stream
            .lock()
            .unwrap_or_else(|poisoned| poisoned.into_inner());
        let size = (pixels.width, pixels.height);
        let fresh = held
            .as_ref()
            .is_none_or(|stream| (stream.width, stream.height) != size);
        if fresh {
            *held = None;
            *held = Some(Stream::new(pixels.width, pixels.height)?);
        }
        let stream = held.as_mut().expect("made above");
        let rects = damage
            .filter(|_| !fresh)
            .map(|damage| block_rects(damage, pixels.width, pixels.height));
        let whole = [(0, 0, pixels.width, pixels.height)];
        for &rect in rects.as_deref().unwrap_or(&whole) {
            stream.take(pixels, rect);
        }
        match stream.encode(rects.as_deref()) {
            Ok(data) => {
                stream.serial = serial;
                let keyframe = rects.is_none();
                Ok((keyframe, data, rects.unwrap_or_else(|| whole.to_vec())))
            }
            Err(error) => {
                // The planes moved on and the stream did not: start again.
                *held = None;
                Err(error)
            }
        }
    }
}
