//! The parent's end of a compositor in a child process: the methods of
//! `Compositor`, answered over the socket. Lillecarl/pyterm#1004.
//!
//! A thread reads the socket. It hands each reply to the call waiting
//! for it, and queues each event, and wakes the descriptor in `fds()`;
//! `dispatch()` then answers the events, as `Compositor.dispatch` does.
//!
//! A call that answers nothing goes without waiting: a key, a pointer
//! move, a frame done. A window id it names is checked against the
//! windows the events said are open, so a closed one raises `KeyError`
//! here, as it would in process. A call that answers waits for it, with
//! the GIL let go; a frame answers an awaitable.

use std::collections::{HashMap, HashSet, VecDeque};
use std::io::{Read, Write};
use std::os::fd::{AsRawFd, FromRawFd, IntoRawFd};
use std::os::unix::net::UnixStream;
use std::sync::atomic::{AtomicBool, AtomicU64, Ordering};
use std::sync::{Arc, Mutex, mpsc};
use std::time::Duration;

use pyo3::exceptions::PyValueError;
use pyo3::prelude::*;
use pysmithay_core::protocol::{Answer, Message, Receiver, Request, Sender, VERSION};
use pysmithay_core::{Error, Event, Result, Target, target_of};

use crate::{PyFrame, event_py, frame_py, kitty_py, py_err, rects_py, video_py};

/// How long a call that answers waits for the child. A child busy past
/// this is stuck, and the caller hears it as an `OSError`.
const ASK_TIMEOUT: Duration = Duration::from_secs(5);

fn lock<T>(mutex: &Mutex<T>) -> std::sync::MutexGuard<'_, T> {
    mutex
        .lock()
        .unwrap_or_else(|poisoned| poisoned.into_inner())
}

enum Waiter {
    Blocking(mpsc::Sender<Result<Answer>>),
    Async(tokio::sync::oneshot::Sender<Result<Answer>>),
}

impl Waiter {
    fn give(self, result: Result<Answer>) {
        match self {
            Self::Blocking(sender) => drop(sender.send(result)),
            Self::Async(sender) => drop(sender.send(result)),
        }
    }
}

/// What the reader thread and the callers share.
struct Shared {
    waiters: Mutex<HashMap<u64, Waiter>>,
    events: Mutex<VecDeque<Event>>,
    /// The windows open, as the events so far say.
    toplevels: Mutex<HashSet<u64>>,
    closed: AtomicBool,
    /// Written once per batch of events; `fds()` names its other end.
    wake: UnixStream,
}

impl Shared {
    /// Until the child closes its end, which it does as it exits.
    fn read(self: Arc<Self>, mut receiver: Receiver, ended: mpsc::Sender<()>) {
        loop {
            match receiver.receive() {
                Ok(Some(Message::Reply { seq, result })) => {
                    if let Some(waiter) = lock(&self.waiters).remove(&seq) {
                        waiter.give(result);
                    }
                }
                Ok(Some(Message::Event(event))) => {
                    match &event {
                        Event::Toplevel(id, _) => {
                            lock(&self.toplevels).insert(*id);
                        }
                        Event::Closed(id) => {
                            lock(&self.toplevels).remove(id);
                        }
                        _ => {}
                    }
                    lock(&self.events).push_back(event);
                    // A full socket already wakes the reader.
                    let _ = (&self.wake).write(&[1]);
                }
                Ok(Some(_)) => {}
                Ok(None) | Err(_) => break,
            }
        }
        self.closed.store(true, Ordering::SeqCst);
        // Every window went with the child.
        lock(&self.toplevels).clear();
        for (_, waiter) in lock(&self.waiters).drain() {
            waiter.give(Err(Error::Closed));
        }
        let _ = (&self.wake).write(&[1]);
        let _ = ended.send(());
    }
}

/// A VP9 stream of one window for one reader, held in the child.
#[pyclass(frozen, module = "pysmithay")]
pub struct RemoteEncoder {
    id: u64,
    sender: Arc<Sender>,
}

impl Drop for RemoteEncoder {
    fn drop(&mut self) {
        let request = Request::DropEncoder { encoder: self.id };
        let _ = self.sender.send(Message::Request { seq: 0, request });
    }
}

/// A compositor in a child process, called as a `Compositor` is.
#[pyclass(frozen, module = "pysmithay")]
pub struct RemoteCompositor {
    sender: Arc<Sender>,
    shared: Arc<Shared>,
    /// The socket, to shut down: the child ends when it reads the end.
    stream: UnixStream,
    woken: UnixStream,
    /// Told when the reader has read the child's end.
    ended: Mutex<Option<mpsc::Receiver<()>>>,
    socket_name: String,
    output: Option<(i32, i32)>,
    /// The protocol the child speaks.
    version: u32,
    next_seq: AtomicU64,
    next_encoder: AtomicU64,
}

/// A failure of a call about window `id`: once the child has gone, the
/// window has too, and the caller hears `KeyError` as for any window
/// that closed. `dispatch` says the child went, once.
fn about(id: u64) -> impl Fn(Error) -> PyErr {
    move |error| match error {
        Error::Closed => py_err(Error::NoWindow(id)),
        error => py_err(error),
    }
}

impl RemoteCompositor {
    /// Send a request that wants no answer. Once the child has gone it
    /// goes nowhere, and says nothing: a key a person presses must not
    /// fail in the client that sent it.
    fn tell(&self, request: Request) -> PyResult<()> {
        if !self.shared.closed.load(Ordering::SeqCst) {
            let _ = self.sender.send(Message::Request { seq: 0, request });
        }
        Ok(())
    }

    fn window(&self, id: u64) -> PyResult<()> {
        if lock(&self.shared.toplevels).contains(&id) {
            Ok(())
        } else {
            Err(py_err(Error::NoWindow(id)))
        }
    }

    fn tell_window(&self, id: u64, request: Request) -> PyResult<()> {
        self.window(id)?;
        self.tell(request)
    }

    fn send_waiting(&self, request: Request, waiter: Waiter) -> Result<()> {
        let seq = self.next_seq.fetch_add(1, Ordering::Relaxed);
        lock(&self.shared.waiters).insert(seq, waiter);
        // After the waiter is in: the reader fails every waiter it finds
        // once it sets `closed`.
        if self.shared.closed.load(Ordering::SeqCst) {
            lock(&self.shared.waiters).remove(&seq);
            return Err(Error::Closed);
        }
        if let Err(error) = self.sender.send(Message::Request { seq, request }) {
            lock(&self.shared.waiters).remove(&seq);
            return Err(error);
        }
        Ok(())
    }

    fn ask(&self, py: Python<'_>, request: Request) -> Result<Answer> {
        let (sender, receiver) = mpsc::channel();
        self.send_waiting(request, Waiter::Blocking(sender))?;
        py.detach(move || match receiver.recv_timeout(ASK_TIMEOUT) {
            Ok(result) => result,
            Err(_) => Err(Error::Os("the compositor did not answer".into())),
        })
    }

    /// An awaitable of the answer about window `id`.
    fn ask_later<'py, T>(
        &self,
        py: Python<'py>,
        id: u64,
        request: Request,
        unwrap: fn(Answer) -> Option<T>,
    ) -> PyResult<Bound<'py, PyAny>>
    where
        T: for<'a> IntoPyObject<'a> + Send + 'static,
    {
        let (sender, receiver) = tokio::sync::oneshot::channel();
        self.send_waiting(request, Waiter::Async(sender))
            .map_err(about(id))?;
        pyo3_async_runtimes::tokio::future_into_py(py, async move {
            let answer = receiver
                .await
                .map_err(|_| Error::Closed)
                .and_then(|result| result)
                .map_err(about(id))?;
            unwrap(answer).ok_or_else(unexpected)
        })
    }
}

fn unexpected() -> PyErr {
    PyValueError::new_err("the compositor answered something else")
}

#[pymethods]
impl RemoteCompositor {
    /// An awaitable of the compositor whose child holds the other end of
    /// the socket `fd`, once it says it listens, within `timeout` seconds.
    /// The child binds its path only once a server it replaces has let
    /// go, so `timeout` outlasts the child's own wait. This owns `fd` now.
    #[staticmethod]
    #[pyo3(signature = (fd, timeout=60.0))]
    fn start(py: Python<'_>, fd: i32, timeout: f64) -> PyResult<Bound<'_, PyAny>> {
        // SAFETY: the caller hands the descriptor over.
        let stream = unsafe { UnixStream::from_raw_fd(fd) };
        let timeout = Duration::try_from_secs_f64(timeout)
            .map_err(|_| PyValueError::new_err("a timeout is a positive number of seconds"))?;
        pyo3_async_runtimes::tokio::future_into_py(py, async move {
            let (sender, receiver) = tokio::sync::oneshot::channel();
            std::thread::spawn(move || drop(sender.send(Self::greeted(stream, timeout))));
            receiver
                .await
                .map_err(|_| py_err(Error::Closed))?
                .map_err(py_err)
        })
    }

    #[getter]
    fn socket_name(&self) -> &str {
        &self.socket_name
    }

    #[getter]
    fn output_size(&self) -> Option<(i32, i32)> {
        self.output
    }

    /// The protocol version the child speaks.
    #[getter]
    fn version(&self) -> u32 {
        self.version
    }

    /// One descriptor to wait on for reading: an event has come.
    fn fds(&self) -> (i32,) {
        (self.woken.as_raw_fd(),)
    }

    /// The events that have come, oldest first, as `Compositor.dispatch`
    /// answers them. Raises `OSError` once the child has gone and every
    /// event it sent was read.
    fn dispatch(&self, py: Python<'_>) -> PyResult<Vec<Py<PyAny>>> {
        let mut drained = [0; 256];
        while matches!((&self.woken).read(&mut drained), Ok(n) if n > 0) {}
        let events: Vec<Event> = lock(&self.shared.events).drain(..).collect();
        if self.shared.closed.load(Ordering::SeqCst) {
            if events.is_empty() {
                return Err(py_err(Error::Closed));
            }
            // The drain above may have taken the reader's last wake, and
            // the caller must still hear that the child went.
            let _ = (&self.shared.wake).write(&[1]);
        }
        events
            .into_iter()
            .map(|event| event_py(py, event))
            .collect()
    }

    /// Let the child go, and wait until it has: it closes every window
    /// and stops listening, and its socket path is gone once this
    /// returns, as after `Compositor.shutdown`. At most `ASK_TIMEOUT`.
    fn shutdown(&self, py: Python<'_>) {
        let _ = self.stream.shutdown(std::net::Shutdown::Write);
        let ended = lock(&self.ended).take();
        if let Some(ended) = ended {
            py.detach(move || {
                let _ = ended.recv_timeout(ASK_TIMEOUT);
            });
        }
        let _ = self.stream.shutdown(std::net::Shutdown::Both);
        self.shared.closed.store(true, Ordering::SeqCst);
        lock(&self.shared.events).clear();
    }

    fn set_selection(
        &self,
        target: &str,
        offers: HashMap<String, Option<Vec<u8>>>,
    ) -> PyResult<()> {
        let target = target_of(target).map_err(py_err)?;
        self.tell(Request::SetSelection {
            target,
            offers: offers.into_iter().collect(),
        })
    }

    fn clear_selection(&self, target: &str) -> PyResult<()> {
        let target = target_of(target).map_err(py_err)?;
        self.tell(Request::ClearSelection { target })
    }

    fn request_selection(&self, py: Python<'_>, target: &str, mime_type: String) -> PyResult<i32> {
        let target: Target = target_of(target).map_err(py_err)?;
        // As for a selection replaced before it was asked for.
        match self.ask(py, Request::RequestSelection { target, mime_type }) {
            Ok(Answer::Fd(fd)) => Ok(fd.into_raw_fd()),
            Ok(_) => Err(unexpected()),
            Err(Error::Closed) => Err(PyValueError::new_err("the compositor is gone")),
            Err(error) => Err(py_err(error)),
        }
    }

    fn focus(&self, id: u64) -> PyResult<()> {
        self.tell_window(id, Request::Focus { id })
    }

    fn key(&self, code: u32, pressed: bool, time: u32) -> PyResult<()> {
        self.tell(Request::Key {
            code,
            pressed,
            time,
        })
    }

    fn commit_text(&self, py: Python<'_>, text: String) -> PyResult<bool> {
        // No window has the keyboard once the child has gone.
        match self.ask(py, Request::CommitText { text }) {
            Ok(Answer::Bool(sent)) => Ok(sent),
            Ok(_) => Err(unexpected()),
            Err(Error::Closed) => Ok(false),
            Err(error) => Err(py_err(error)),
        }
    }

    fn pointer_motion(&self, id: u64, x: f64, y: f64, time: u32) -> PyResult<()> {
        self.tell_window(id, Request::PointerMotion { id, x, y, time })
    }

    fn pointer_leave(&self, id: u64, time: u32) -> PyResult<()> {
        self.tell(Request::PointerLeave { id, time })
    }

    #[pyo3(signature = (steps, time, horizontal=false))]
    fn pointer_scroll(&self, steps: i32, time: u32, horizontal: bool) -> PyResult<()> {
        self.tell(Request::PointerScroll {
            steps,
            time,
            horizontal,
        })
    }

    #[pyo3(signature = (id, pixels, time, horizontal=false))]
    fn pointer_scroll_smooth(
        &self,
        id: u64,
        pixels: f64,
        time: u32,
        horizontal: bool,
    ) -> PyResult<()> {
        self.tell_window(
            id,
            Request::PointerScrollSmooth {
                id,
                pixels,
                time,
                horizontal,
            },
        )
    }

    fn pointer_button(&self, button: u32, pressed: bool, time: u32) -> PyResult<()> {
        self.tell(Request::PointerButton {
            button,
            pressed,
            time,
        })
    }

    fn connect(&self, py: Python<'_>) -> PyResult<(u64, i32)> {
        match self.ask(py, Request::Connect).map_err(py_err)? {
            Answer::Connected(tag, fd) => Ok((tag, fd.into_raw_fd())),
            _ => Err(unexpected()),
        }
    }

    #[pyo3(signature = (id, width, height, scale=1.0))]
    fn configure(&self, id: u64, width: i32, height: i32, scale: f64) -> PyResult<()> {
        if !(scale.is_finite() && scale > 0.0) {
            return Err(py_err(Error::Value(format!(
                "a scale is a positive number, not {scale}"
            ))));
        }
        self.tell_window(
            id,
            Request::Configure {
                id,
                width,
                height,
                scale,
            },
        )
    }

    fn close(&self, id: u64) -> PyResult<()> {
        self.tell_window(id, Request::Close { id })
    }

    fn frame_done(&self, id: u64, time: u32) -> PyResult<()> {
        self.tell_window(id, Request::FrameDone { id, time })
    }

    fn wants_frame(&self, py: Python<'_>, id: u64) -> PyResult<bool> {
        self.window(id)?;
        match self
            .ask(py, Request::WantsFrame { id })
            .map_err(about(id))?
        {
            Answer::Bool(wants) => Ok(wants),
            _ => Err(unexpected()),
        }
    }

    fn toplevels(&self, py: Python<'_>) -> PyResult<Vec<u64>> {
        match self.ask(py, Request::Toplevels) {
            Ok(Answer::Ids(ids)) => Ok(ids),
            Ok(_) => Err(unexpected()),
            Err(Error::Closed) => Ok(Vec::new()),
            Err(error) => Err(py_err(error)),
        }
    }

    fn frame(&self, py: Python<'_>, id: u64) -> PyResult<PyFrame> {
        self.window(id)?;
        match self.ask(py, Request::Frame { id }).map_err(about(id))? {
            Answer::Frame(frame) => Ok(frame_py(frame)),
            _ => Err(unexpected()),
        }
    }

    #[pyo3(signature = (id, image_id, since=None))]
    fn kitty_update<'py>(
        &self,
        py: Python<'py>,
        id: u64,
        image_id: u32,
        since: Option<u64>,
    ) -> PyResult<Bound<'py, PyAny>> {
        self.window(id)?;
        let request = Request::KittyUpdate {
            id,
            image_id,
            since,
        };
        self.ask_later(py, id, request, |answer| match answer {
            Answer::Kitty(update) => Some(kitty_py(update)),
            _ => None,
        })
    }

    #[pyo3(signature = (id, since=None))]
    fn frame_rects<'py>(
        &self,
        py: Python<'py>,
        id: u64,
        since: Option<u64>,
    ) -> PyResult<Bound<'py, PyAny>> {
        self.window(id)?;
        self.ask_later(
            py,
            id,
            Request::FrameRects { id, since },
            |answer| match answer {
                Answer::Rects(rects) => Some(rects_py(rects)),
                _ => None,
            },
        )
    }

    fn vp9_frame<'py>(
        &self,
        py: Python<'py>,
        id: u64,
        encoder: PyRef<'py, RemoteEncoder>,
    ) -> PyResult<Bound<'py, PyAny>> {
        self.window(id)?;
        let request = Request::Vp9Frame {
            id,
            encoder: encoder.id,
        };
        self.ask_later(py, id, request, |answer| match answer {
            Answer::Video(frame) => Some(video_py(frame)),
            _ => None,
        })
    }

    /// A new encoder for `vp9_frame`, for one reader; the child holds it.
    fn vp9_encoder(&self) -> RemoteEncoder {
        RemoteEncoder {
            id: self.next_encoder.fetch_add(1, Ordering::Relaxed),
            sender: self.sender.clone(),
        }
    }
}

impl RemoteCompositor {
    /// Wait for the child's first word, and start reading after it.
    fn greeted(stream: UnixStream, timeout: Duration) -> Result<Self> {
        let reader = stream.try_clone()?;
        reader.set_read_timeout(Some(timeout))?;
        let mut receiver = Receiver::new(reader.try_clone()?);
        let (version, socket_name, output) = match receiver.receive() {
            Ok(Some(Message::Hello {
                version,
                socket_name,
                output,
            })) => (version, socket_name, output),
            Ok(Some(Message::Failed(error))) => return Err(error),
            Ok(Some(_)) => return Err(Error::Os("the compositor spoke out of turn".into())),
            Ok(None) => return Err(Error::Os("the compositor ended before it listened".into())),
            Err(error) => return Err(Error::Os(format!("the compositor never listened: {error}"))),
        };
        if version != VERSION {
            return Err(Error::Os(format!(
                "the compositor speaks version {version}, and this build {VERSION}"
            )));
        }
        reader.set_read_timeout(None)?;
        let (wake, woken) = UnixStream::pair()?;
        wake.set_nonblocking(true)?;
        woken.set_nonblocking(true)?;
        let shared = Arc::new(Shared {
            waiters: Mutex::new(HashMap::new()),
            events: Mutex::new(VecDeque::new()),
            toplevels: Mutex::new(HashSet::new()),
            closed: AtomicBool::new(false),
            wake,
        });
        let reading = shared.clone();
        let (ending, ended) = mpsc::channel();
        std::thread::Builder::new()
            .name("pysmithay-remote".into())
            .spawn(move || reading.read(receiver, ending))?;
        Ok(Self {
            sender: Arc::new(Sender::new(stream.try_clone()?)),
            shared,
            stream,
            woken,
            ended: Mutex::new(Some(ended)),
            socket_name,
            output,
            version,
            next_seq: AtomicU64::new(1),
            next_encoder: AtomicU64::new(1),
        })
    }
}

impl Drop for RemoteCompositor {
    fn drop(&mut self) {
        let _ = self.stream.shutdown(std::net::Shutdown::Both);
    }
}
