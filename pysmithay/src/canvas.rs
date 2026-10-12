//! A window drawn whole: its surface, its subsurfaces and its popups,
//! composed by Smithay's pixman renderer into one RGBA picture, with the
//! rectangles that changed since the last frame.
//!
//! The damage comes from `OutputDamageTracker`, which follows every
//! surface of the window -- one that moved, appeared or went counts as
//! well as one that drew -- so what a reader is sent is exactly what
//! differs from the frame it holds.

use smithay::backend::allocator::Fourcc;
use smithay::backend::renderer::damage::OutputDamageTracker;
use smithay::backend::renderer::element::AsRenderElements;
use smithay::backend::renderer::element::surface::WaylandSurfaceRenderElement;
use smithay::backend::renderer::pixman::PixmanRenderer;
use smithay::backend::renderer::{Bind, Color32F, Offscreen};
use smithay::desktop::Window;
use smithay::reexports::pixman::Image;
use smithay::utils::{Physical, Point, Scale, Transform};

use crate::Rect;
use crate::kitty::Pixels;

/// What shows where no surface covers the canvas. Opaque, so every
/// frame is too and goes as three bytes a pixel.
const CLEAR: Color32F = Color32F::new(0.0, 0.0, 0.0, 1.0);

pub struct Canvas {
    image: Image<'static, 'static>,
    tracker: OutputDamageTracker,
    pub width: i32,
    pub height: i32,
    /// Canvas pixels per logical pixel of the window.
    pub scale: f64,
    /// Whether the image holds the last frame, so the next one draws
    /// only what changed.
    drawn: bool,
}

impl Canvas {
    /// An empty canvas, or none for a size pixman cannot make.
    pub fn new(renderer: &mut PixmanRenderer, width: i32, height: i32, scale: f64) -> Option<Self> {
        // Abgr8888 is R, G, B, A in memory on a little-endian machine:
        // the order the kitty encoder reads.
        let image = renderer
            .create_buffer(Fourcc::Abgr8888, (width, height).into())
            .ok()?;
        Some(Self {
            image,
            tracker: OutputDamageTracker::new((width, height), scale, Transform::Normal),
            width,
            height,
            scale,
            drawn: false,
        })
    }

    /// Draw the window as it is now, and return what changed: all of it
    /// the first time, nothing when nothing did.
    ///
    /// The window's geometry lands at the canvas origin, so a shadow or
    /// a margin outside it is cut off, as a desktop would show it.
    pub fn render(&mut self, renderer: &mut PixmanRenderer, window: &Window) -> Vec<Rect> {
        let origin: Point<i32, Physical> =
            window.geometry().loc.to_physical_precise_round(self.scale);
        let elements: Vec<WaylandSurfaceRenderElement<PixmanRenderer>> = window.render_elements(
            renderer,
            (-origin.x, -origin.y).into(),
            Scale::from(self.scale),
            1.0,
        );
        let Ok(mut target) = renderer.bind(&mut self.image) else {
            return Vec::new();
        };
        let age = usize::from(self.drawn);
        let Ok(result) = self
            .tracker
            .render_output(renderer, &mut target, age, &elements, CLEAR)
        else {
            return Vec::new();
        };
        self.drawn = true;
        result
            .damage
            .map(|damage| {
                damage
                    .iter()
                    .map(|rect| (rect.loc.x, rect.loc.y, rect.size.w, rect.size.h))
                    .collect()
            })
            .unwrap_or_default()
    }

    /// The picture as the encoder reads it.
    pub fn pixels(&self) -> Pixels<'_> {
        let stride = self.image.stride();
        // SAFETY: pixman owns `height` rows of `stride` bytes for as long
        // as the image lives, and the borrow of `self` outlives this view.
        let bytes = unsafe {
            std::slice::from_raw_parts(self.image.data().cast::<u8>(), stride * self.image.height())
        };
        Pixels {
            width: self.width,
            height: self.height,
            stride,
            rgba: bytes,
            opaque: true,
        }
    }
}
