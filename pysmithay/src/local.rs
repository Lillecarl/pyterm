//! A compositor in this process.
//!
//! Python owns the event loop. It waits for either file descriptor in
//! `fds()` to become readable and then calls `dispatch()`, which accepts
//! new clients, runs their requests and returns what happened.

use std::collections::HashMap;
use std::os::fd::IntoRawFd;

use pyo3::prelude::*;
use pysmithay_core as core;

use crate::{
    PyFrame, Vp9Encoder, awaitable, event_py, frame_py, kitty_py, py_err, rects_py, video_py,
};

/// A Wayland compositor that draws nowhere, and hands every window's
/// pixels to Python.
///
/// `unsendable`, and `shutdown` drops the sockets on the thread that
/// owns it: PyO3 runs no destructor of an `unsendable` class freed on
/// another thread, and Python's garbage collector may free one on any.
/// Lillecarl/pyterm#644.
#[pyclass(unsendable, module = "pysmithay")]
pub struct Compositor {
    pub(crate) inner: core::Compositor,
}

#[pymethods]
impl Compositor {
    /// Listen on `$XDG_RUNTIME_DIR/<socket_name>`, on `socket_name`
    /// itself when it is an absolute path, or on the first free
    /// `wayland-N` when no name is given.
    #[new]
    #[pyo3(signature = (socket_name=None, width=800, height=600))]
    fn new(socket_name: Option<&str>, width: i32, height: i32) -> PyResult<Self> {
        Ok(Self {
            inner: core::Compositor::new(socket_name, width, height).map_err(py_err)?,
        })
    }

    /// Hold a selection for clients to paste: each mime type with its
    /// bytes. `target` is "clipboard" or "primary".
    ///
    /// A mime type offered with None is answered by Python: a paste of
    /// it comes back from `dispatch` as `("send", target, mime_type,
    /// fd)`, and the caller writes the bytes into `fd` and closes it.
    fn set_selection(
        &mut self,
        target: &str,
        offers: HashMap<String, Option<Vec<u8>>>,
    ) -> PyResult<()> {
        self.inner.set_selection(target, offers).map_err(py_err)
    }

    /// Drop the selection, whoever set it.
    fn clear_selection(&mut self, target: &str) -> PyResult<()> {
        self.inner.clear_selection(target).map_err(py_err)
    }

    /// Ask the client that holds the selection for it in `mime_type`.
    ///
    /// Returns the read end of a pipe, which the caller owns and reads
    /// to the end. The client writes only once `dispatch` has run, so
    /// read it without blocking the loop that calls `dispatch`.
    fn request_selection(&mut self, target: &str, mime_type: String) -> PyResult<i32> {
        Ok(self
            .inner
            .request_selection(target, mime_type)
            .map_err(py_err)?
            .into_raw_fd())
    }

    /// Give the keyboard to this window, unless a menu holds it.
    fn focus(&mut self, id: u64) -> PyResult<()> {
        self.inner.focus(id).map_err(py_err)
    }

    /// Press or release a key, as a Linux evdev key code.
    fn key(&mut self, code: u32, pressed: bool, time: u32) -> PyResult<()> {
        self.inner.key(code, pressed, time).map_err(py_err)
    }

    /// Give `text` to the window with the keyboard, through its
    /// `zwp_text_input_v3`. False when it has none. Lillecarl/pyterm#626.
    fn commit_text(&mut self, text: &str) -> PyResult<bool> {
        self.inner.commit_text(text).map_err(py_err)
    }

    /// Move the pointer to `(x, y)` in the window's canvas pixels.
    fn pointer_motion(&mut self, id: u64, x: f64, y: f64, time: u32) -> PyResult<()> {
        self.inner.pointer_motion(id, x, y, time).map_err(py_err)
    }

    /// The pointer left window `id`.
    fn pointer_leave(&mut self, id: u64, time: u32) -> PyResult<()> {
        self.inner.pointer_leave(id, time).map_err(py_err)
    }

    /// Scroll the wheel by `steps` notches.
    #[pyo3(signature = (steps, time, horizontal=false))]
    fn pointer_scroll(&mut self, steps: i32, time: u32, horizontal: bool) -> PyResult<()> {
        self.inner
            .pointer_scroll(steps, time, horizontal)
            .map_err(py_err)
    }

    /// Scroll window `id` by `pixels` of its canvas, as a continuous source.
    #[pyo3(signature = (id, pixels, time, horizontal=false))]
    fn pointer_scroll_smooth(
        &mut self,
        id: u64,
        pixels: f64,
        time: u32,
        horizontal: bool,
    ) -> PyResult<()> {
        self.inner
            .pointer_scroll_smooth(id, pixels, time, horizontal)
            .map_err(py_err)
    }

    /// Press or release a pointer button, as an evdev code.
    fn pointer_button(&mut self, button: u32, pressed: bool, time: u32) -> PyResult<()> {
        self.inner
            .pointer_button(button, pressed, time)
            .map_err(py_err)
    }

    /// What a client puts in `WAYLAND_DISPLAY`.
    #[getter]
    fn socket_name(&self) -> &str {
        self.inner.socket_name()
    }

    /// The listening socket and the display: wait on both for reading.
    fn fds(&mut self) -> PyResult<(i32, i32)> {
        self.inner.fds().map_err(py_err)
    }

    /// Let every client go and stop listening. Nothing works after it.
    fn shutdown(&mut self) {
        self.inner.shutdown();
    }

    /// A client connected already, for a program to take as
    /// `WAYLAND_SOCKET`: `(tag, fd)`. The caller owns `fd`.
    fn connect(&mut self) -> PyResult<(u64, i32)> {
        let (tag, fd) = self.inner.connect().map_err(py_err)?;
        Ok((tag, fd.into_raw_fd()))
    }

    /// Accept waiting clients, run every request that has arrived, and
    /// return what happened, oldest first.
    ///
    /// Each event is a tuple: `("toplevel", id, tag)`, `("title", id, str)`,
    /// `("app_id", id, str)`, `("pointer", id, css_name)` with "" for a
    /// pointer the terminal picks, `("commit", id, [(x, y, w, h), ...])` with
    /// the damage in canvas pixels, empty when the commit drew nothing
    /// but may wait on `frame_done` all the same, `("closed", id)`, or
    /// `("selection", "clipboard" | "primary", [mime types])` when a
    /// client sets a selection, with no mime types when it clears one,
    /// or `("send", target, mime_type, fd)` when a client pastes a mime
    /// type held with None; the caller owns `fd` and must close it.
    fn dispatch(&mut self, py: Python<'_>) -> PyResult<Vec<Py<PyAny>>> {
        let events = self.inner.dispatch().map_err(py_err)?;
        events
            .into_iter()
            .map(|event| event_py(py, event))
            .collect()
    }

    /// An awaitable of `(serial, commands, whole)`: what a kitty graphics
    /// terminal needs to show the window as image `image_id`, given the
    /// serial of the last frame it was sent. Lillecarl/pyterm#633.
    #[pyo3(signature = (id, image_id, since=None))]
    fn kitty_update<'py>(
        &self,
        py: Python<'py>,
        id: u64,
        image_id: u32,
        since: Option<u64>,
    ) -> PyResult<Bound<'py, PyAny>> {
        let work = self
            .inner
            .kitty_update(id, image_id, since)
            .map_err(py_err)?;
        awaitable(py, work, kitty_py)
    }

    /// An awaitable of `(serial, whole, width, height, rects)`, or None
    /// before the window has drawn: the RGB pixels a reader needs to
    /// bring the window up to date. Lillecarl/pyterm#636.
    #[pyo3(signature = (id, since=None))]
    fn frame_rects<'py>(
        &self,
        py: Python<'py>,
        id: u64,
        since: Option<u64>,
    ) -> PyResult<Bound<'py, PyAny>> {
        let work = self.inner.frame_rects(id, since).map_err(py_err)?;
        awaitable(py, work, rects_py)
    }

    /// An awaitable of the window's next frame in `encoder`'s VP9 stream:
    /// `(serial, keyframe, width, height, data, rects)`, or None before
    /// the window has drawn. Lillecarl/pyterm#641.
    fn vp9_frame<'py>(
        &self,
        py: Python<'py>,
        id: u64,
        encoder: PyRef<'py, Vp9Encoder>,
    ) -> PyResult<Bound<'py, PyAny>> {
        let work = self
            .inner
            .vp9_frame(id, encoder.inner.clone())
            .map_err(py_err)?;
        awaitable(py, work, video_py)
    }

    /// A new encoder for `vp9_frame`, for one reader.
    fn vp9_encoder(&self) -> Vp9Encoder {
        Vp9Encoder::default()
    }

    /// The window as last drawn, as `(width, height, rgba)` with no row
    /// padding, or None before it has drawn.
    fn frame(&self, id: u64) -> PyResult<PyFrame> {
        Ok(frame_py(self.inner.frame(id).map_err(py_err)?))
    }

    /// Ask the window to fill a canvas this size, in pixels, at `scale`
    /// canvas pixels to one of its own.
    #[pyo3(signature = (id, width, height, scale=1.0))]
    fn configure(&mut self, id: u64, width: i32, height: i32, scale: f64) -> PyResult<()> {
        self.inner
            .configure(id, width, height, scale)
            .map_err(py_err)
    }

    /// Ask the window to close. The client decides.
    fn close(&mut self, id: u64) -> PyResult<()> {
        self.inner.close(id).map_err(py_err)
    }

    /// Tell one window, its popups included, that its last frame was
    /// shown, so it may draw the next.
    fn frame_done(&mut self, id: u64, time: u32) -> PyResult<()> {
        self.inner.frame_done(id, time).map_err(py_err)
    }

    /// Whether the window asked to be told when to draw next and was
    /// not told yet.
    fn wants_frame(&self, id: u64) -> PyResult<bool> {
        self.inner.wants_frame(id).map_err(py_err)
    }

    /// The ids of the windows that are open, oldest first.
    fn toplevels(&self) -> Vec<u64> {
        self.inner.toplevels()
    }

    /// The output's size in pixels, which a client reads as its screen.
    #[getter]
    fn output_size(&self) -> Option<(i32, i32)> {
        self.inner.output_size()
    }
}
