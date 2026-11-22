//! `pysmithay._native`: the compositor of `pysmithay-core`, for Python.
//!
//! Three ways to hold one, with the same methods:
//!
//! - `Compositor`, in this process.
//! - `Channel`, the child's end of a compositor in a child process: it
//!   answers the parent's requests from a `Compositor`, and does the
//!   encodes and the frame bytes here, never in Python.
//! - `RemoteCompositor`, the parent's end, which `wayland.py` calls as
//!   it calls a `Compositor`. Lillecarl/pyterm#1004.

use std::sync::Arc;

use pyo3::exceptions::{PyKeyError, PyOSError, PyRuntimeError, PyValueError};
use pyo3::prelude::*;
use pyo3::types::PyBytes;
use pysmithay_core::{
    Error, Event, Frame, FrameRects, KittyUpdate, Rect, VideoFrame, Work, name_of,
};

mod channel;
mod local;
mod remote;

fn py_err(error: Error) -> PyErr {
    match error {
        Error::NoWindow(id) => PyKeyError::new_err(id),
        Error::Closed => PyOSError::new_err(Error::Closed.to_string()),
        Error::Os(text) => PyOSError::new_err(text),
        Error::Value(text) => PyValueError::new_err(text),
        Error::Encode(text) => PyRuntimeError::new_err(text),
    }
}

/// Pixels that go to Python as `bytes`, and not as a list of ints.
struct Bytes(Vec<u8>);

impl<'py> IntoPyObject<'py> for Bytes {
    type Target = PyBytes;
    type Output = Bound<'py, PyBytes>;
    type Error = std::convert::Infallible;

    fn into_pyobject(self, py: Python<'py>) -> Result<Self::Output, Self::Error> {
        Ok(PyBytes::new(py, &self.0))
    }
}

type PyFrameRects = Option<(u64, bool, i32, i32, Vec<(i32, i32, i32, i32, Bytes)>)>;
type PyVideoFrame = Option<(u64, bool, i32, i32, Bytes, Vec<Rect>)>;
type PyFrame = Option<(i32, i32, Bytes)>;

fn kitty_py(update: KittyUpdate) -> KittyUpdate {
    update
}

fn rects_py(rects: FrameRects) -> PyFrameRects {
    rects.map(|(serial, whole, width, height, rects)| {
        let rects = rects
            .into_iter()
            .map(|(x, y, w, h, pixels)| (x, y, w, h, Bytes(pixels)))
            .collect();
        (serial, whole, width, height, rects)
    })
}

fn video_py(frame: VideoFrame) -> PyVideoFrame {
    frame.map(|(serial, keyframe, width, height, data, rects)| {
        (serial, keyframe, width, height, Bytes(data), rects)
    })
}

fn frame_py(frame: Frame) -> PyFrame {
    frame.map(|(width, height, rgba)| (width, height, Bytes(rgba)))
}

/// An awaitable of `work`'s answer: an encode runs on a worker thread,
/// which the event loop that awaits it does not wait for.
fn awaitable<'py, T, U>(
    py: Python<'py>,
    work: Work<T>,
    convert: fn(T) -> U,
) -> PyResult<Bound<'py, PyAny>>
where
    T: Send + 'static,
    U: for<'a> IntoPyObject<'a> + Send + 'static,
{
    match work {
        Work::Ready(value) => {
            let value = convert(value);
            pyo3_async_runtimes::tokio::future_into_py(py, async move { Ok(value) })
        }
        Work::Later(work) => pyo3_async_runtimes::tokio::future_into_py(py, async move {
            let value = tokio::task::spawn_blocking(work)
                .await
                .map_err(|error| PyRuntimeError::new_err(error.to_string()))?
                .map_err(py_err)?;
            Ok(convert(value))
        }),
    }
}

/// One event of `dispatch`, as the tuple Python reads.
fn event_py(py: Python<'_>, event: Event) -> PyResult<Py<PyAny>> {
    use std::os::fd::IntoRawFd;
    Ok(match event {
        Event::Toplevel(id, origin, pid) => {
            ("toplevel", id, origin, pid).into_pyobject(py)?.into_any()
        }
        Event::Title(id, title) => ("title", id, title).into_pyobject(py)?.into_any(),
        Event::AppId(id, app_id) => ("app_id", id, app_id).into_pyobject(py)?.into_any(),
        Event::Commit(id, damage) => ("commit", id, damage).into_pyobject(py)?.into_any(),
        Event::Closed(id) => ("closed", id).into_pyobject(py)?.into_any(),
        Event::Pointer(id, name) => ("pointer", id, name).into_pyobject(py)?.into_any(),
        Event::Selection(target, mime_types) => ("selection", name_of(target), mime_types)
            .into_pyobject(py)?
            .into_any(),
        Event::Send(target, mime_type, fd) => {
            ("send", name_of(target), mime_type, fd.into_raw_fd())
                .into_pyobject(py)?
                .into_any()
        }
    }
    .unbind())
}

/// One reader's VP9 stream of one window. A stream holds the frames it
/// sent as its reference, so every reader has an encoder of its own.
#[pyclass(name = "Vp9Encoder", frozen, module = "pysmithay")]
#[derive(Default)]
struct Vp9Encoder {
    inner: Arc<pysmithay_core::vp9::Vp9Encoder>,
}

#[pymethods]
impl Vp9Encoder {
    #[new]
    fn new() -> Self {
        Self::default()
    }
}

#[pymodule]
fn _native(module: &Bound<'_, PyModule>) -> PyResult<()> {
    module.add_class::<local::Compositor>()?;
    module.add_class::<Vp9Encoder>()?;
    module.add_class::<channel::Channel>()?;
    module.add_class::<channel::HostRequest>()?;
    module.add_class::<remote::RemoteCompositor>()?;
    module.add_class::<remote::RemoteEncoder>()
}
