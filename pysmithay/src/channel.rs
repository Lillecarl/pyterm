//! The child's end of a compositor in a child process.
//!
//! Python runs the child's loop and routes each request: `requests()`
//! reads what came, and `answer()` carries one out on the compositor
//! and sends the reply. An encode runs on a worker thread and writes its
//! reply itself, so no frame and no pixel passes through Python.
//! `pysmithay.host` is that loop.
//!
//! Every write goes through the `Gate`, so `Pause` stops all of them at
//! a message boundary, an encode's reply too.

use std::collections::HashMap;
use std::os::fd::FromRawFd;
use std::os::unix::net::UnixStream;
use std::sync::{Arc, Mutex};

use pyo3::prelude::*;
use pysmithay_core::protocol::{Answer, Message, Receiver, Request, Sender, VERSION};
use pysmithay_core::vp9::Vp9Encoder;
use pysmithay_core::{Compositor, Error, Event, Result, Work, name_of};

use crate::local;
use crate::py_err;

/// One request from the parent, as `Channel.requests` reads it.
#[pyclass(frozen, module = "pysmithay")]
pub struct HostRequest {
    seq: u64,
    request: Request,
}

#[pymethods]
impl HostRequest {
    /// 0 when the parent wants no answer.
    #[getter]
    fn seq(&self) -> u64 {
        self.seq
    }

    /// The `Compositor` method it names.
    #[getter]
    fn name(&self) -> &'static str {
        match self.request {
            Request::SetSelection { .. } => "set_selection",
            Request::ClearSelection { .. } => "clear_selection",
            Request::RequestSelection { .. } => "request_selection",
            Request::Focus { .. } => "focus",
            Request::Key { .. } => "key",
            Request::CommitText { .. } => "commit_text",
            Request::PointerMotion { .. } => "pointer_motion",
            Request::PointerLeave { .. } => "pointer_leave",
            Request::PointerScroll { .. } => "pointer_scroll",
            Request::PointerScrollSmooth { .. } => "pointer_scroll_smooth",
            Request::PointerButton { .. } => "pointer_button",
            Request::Connect => "connect",
            Request::Configure { .. } => "configure",
            Request::Close { .. } => "close",
            Request::FrameDone { .. } => "frame_done",
            Request::WantsFrame { .. } => "wants_frame",
            Request::Toplevels => "toplevels",
            Request::Frame { .. } => "frame",
            Request::KittyUpdate { .. } => "kitty_update",
            Request::FrameRects { .. } => "frame_rects",
            Request::Vp9Frame { .. } => "vp9_frame",
            Request::DropEncoder { .. } => "drop_encoder",
            Request::Pause => "pause",
            Request::Adopt => "adopt",
            Request::Unknown(_) => "unknown",
        }
    }

    fn __repr__(&self) -> String {
        format!("<HostRequest {} {:?}>", self.seq, self.request)
    }
}

/// What carrying out a request gives: an answer, or an encode to run.
enum Outcome {
    Now(Result<Answer>),
    Later(Box<dyn FnOnce() -> Result<Answer> + Send>),
}

fn unit(result: Result<()>) -> Outcome {
    Outcome::Now(result.map(|()| Answer::Unit))
}

fn later<T: 'static>(work: Result<Work<T>>, wrap: fn(T) -> Answer) -> Outcome {
    match work {
        Err(error) => Outcome::Now(Err(error)),
        Ok(Work::Ready(value)) => Outcome::Now(Ok(wrap(value))),
        Ok(Work::Later(work)) => Outcome::Later(Box::new(move || work().map(wrap))),
    }
}

fn carry_out(
    compositor: &mut Compositor,
    encoders: &Mutex<HashMap<u64, Arc<Vp9Encoder>>>,
    request: Request,
) -> Outcome {
    match request {
        Request::SetSelection { target, offers } => {
            unit(compositor.set_selection(name_of(target), offers.into_iter().collect()))
        }
        Request::ClearSelection { target } => unit(compositor.clear_selection(name_of(target))),
        Request::RequestSelection { target, mime_type } => Outcome::Now(
            compositor
                .request_selection(name_of(target), mime_type)
                .map(Answer::Fd),
        ),
        Request::Focus { id } => unit(compositor.focus(id)),
        Request::Key {
            code,
            pressed,
            time,
        } => unit(compositor.key(code, pressed, time)),
        Request::CommitText { text } => {
            Outcome::Now(compositor.commit_text(&text).map(Answer::Bool))
        }
        Request::PointerMotion { id, x, y, time } => {
            unit(compositor.pointer_motion(id, x, y, time))
        }
        Request::PointerLeave { id, time } => unit(compositor.pointer_leave(id, time)),
        Request::PointerScroll {
            steps,
            time,
            horizontal,
        } => unit(compositor.pointer_scroll(steps, time, horizontal)),
        Request::PointerScrollSmooth {
            id,
            pixels,
            time,
            horizontal,
        } => unit(compositor.pointer_scroll_smooth(id, pixels, time, horizontal)),
        Request::PointerButton {
            button,
            pressed,
            time,
        } => unit(compositor.pointer_button(button, pressed, time)),
        Request::Connect => Outcome::Now(
            compositor
                .connect()
                .map(|(tag, fd)| Answer::Connected(tag, fd)),
        ),
        Request::Configure {
            id,
            width,
            height,
            scale,
        } => unit(compositor.configure(id, width, height, scale)),
        Request::Close { id } => unit(compositor.close(id)),
        Request::FrameDone { id, time } => unit(compositor.frame_done(id, time)),
        Request::WantsFrame { id } => Outcome::Now(compositor.wants_frame(id).map(Answer::Bool)),
        Request::Toplevels => Outcome::Now(Ok(Answer::Ids(compositor.toplevels()))),
        // The copy out of the canvas is the whole cost; it goes as it is.
        Request::Frame { id } => Outcome::Now(compositor.frame(id).map(Answer::Frame)),
        Request::KittyUpdate {
            id,
            image_id,
            since,
        } => later(compositor.kitty_update(id, image_id, since), Answer::Kitty),
        Request::FrameRects { id, since } => {
            later(compositor.frame_rects(id, since), Answer::Rects)
        }
        Request::Vp9Frame { id, encoder } => {
            let encoder = encoders
                .lock()
                .unwrap_or_else(|poisoned| poisoned.into_inner())
                .entry(encoder)
                .or_default()
                .clone();
            later(compositor.vp9_frame(id, encoder), Answer::Video)
        }
        Request::DropEncoder { encoder } => {
            encoders
                .lock()
                .unwrap_or_else(|poisoned| poisoned.into_inner())
                .remove(&encoder);
            Outcome::Now(Ok(Answer::Unit))
        }
        Request::Unknown(tag) => Outcome::Now(Err(Error::Value(format!(
            "this compositor is older than request {tag}"
        )))),
        Request::Pause | Request::Adopt => unreachable!("the channel answers these itself"),
    }
}

fn lock<T>(mutex: &Mutex<T>) -> std::sync::MutexGuard<'_, T> {
    mutex
        .lock()
        .unwrap_or_else(|poisoned| poisoned.into_inner())
}

/// Whether a held event still goes out at `Adopt`: the windows in its
/// answer stand for the rest.
fn outlives_a_pause(event: &Event) -> bool {
    matches!(
        event,
        Event::Selection(..) | Event::Send(..) | Event::Pointer(..)
    )
}

/// What every write of the child goes through.
#[derive(Default)]
struct Gate {
    /// Counts the pauses. The reply of an encode that began before the
    /// last one goes nowhere: the parent that asked is gone.
    epoch: u64,
    /// The events since a `Pause`, while the child writes nothing.
    held: Option<Vec<Event>>,
}

/// The child's end of the socket to the parent.
#[pyclass(frozen, module = "pysmithay")]
pub struct Channel {
    fd: i32,
    sender: Arc<Sender>,
    receiver: Mutex<Receiver>,
    encoders: Mutex<HashMap<u64, Arc<Vp9Encoder>>>,
    gate: Arc<Mutex<Gate>>,
}

impl Channel {
    fn reply(sender: &Sender, gate: &Mutex<Gate>, epoch: u64, seq: u64, result: Result<Answer>) {
        // A request that wanted no answer drops its failure: a key for a
        // window that closed on the way is no fault of anybody's.
        if seq == 0 {
            return;
        }
        let gate = lock(gate);
        if gate.epoch != epoch || gate.held.is_some() {
            return;
        }
        // A parent that went away hears nothing, and `requests` says so.
        let _ = sender.send(Message::Reply { seq, result });
    }

    fn pause(&self, seq: u64) {
        let mut gate = lock(&self.gate);
        gate.epoch += 1;
        if seq != 0 {
            let _ = self.sender.send(Message::Reply {
                seq,
                result: Ok(Answer::Unit),
            });
        }
        gate.held.get_or_insert_with(Vec::new);
    }

    fn adopt(&self, compositor: &Compositor, seq: u64) {
        let mut gate = lock(&self.gate);
        lock(&self.encoders).clear();
        let held = gate.held.take().unwrap_or_default();
        if seq != 0 {
            let answer = Answer::Adopted {
                socket_name: compositor.socket_name().to_owned(),
                output: compositor.output_size(),
                windows: compositor.windows(),
            };
            let _ = self.sender.send(Message::Reply {
                seq,
                result: Ok(answer),
            });
        }
        for event in held {
            let _ = self.sender.send(Message::Event(event));
        }
    }
}

#[pymethods]
impl Channel {
    /// Take the socket `fd`, which the parent passed: this owns it now.
    #[new]
    fn new(fd: i32) -> PyResult<Self> {
        // SAFETY: the caller hands the descriptor over, and nothing else
        // in this process closes it.
        let stream = unsafe { UnixStream::from_raw_fd(fd) };
        let writer = stream
            .try_clone()
            .map_err(|error| py_err(Error::from(error)))?;
        Ok(Self {
            fd,
            sender: Arc::new(Sender::new(writer)),
            receiver: Mutex::new(Receiver::new(stream)),
            encoders: Mutex::new(HashMap::new()),
            gate: Arc::default(),
        })
    }

    /// What to wait on for reading: a request has come.
    fn fileno(&self) -> i32 {
        self.fd
    }

    /// Tell the parent the compositor listens.
    fn hello(&self, compositor: PyRef<'_, local::Compositor>) -> PyResult<()> {
        self.sender
            .send(Message::Hello {
                version: VERSION,
                socket_name: compositor.inner.socket_name().to_owned(),
                output: compositor.inner.output_size(),
            })
            .map_err(py_err)
    }

    /// Tell the parent there is no compositor, and why.
    fn failed(&self, why: String) -> PyResult<()> {
        self.sender
            .send(Message::Failed(Error::Os(why)))
            .map_err(py_err)
    }

    /// Every request that has come, without waiting, and whether the
    /// parent is still there.
    fn requests(&self) -> PyResult<(Vec<HostRequest>, bool)> {
        let (messages, alive) = self
            .receiver
            .lock()
            .unwrap_or_else(|poisoned| poisoned.into_inner())
            .ready()
            .map_err(py_err)?;
        let requests = messages
            .into_iter()
            .filter_map(|message| match message {
                Message::Request { seq, request } => Some(HostRequest { seq, request }),
                _ => None,
            })
            .collect();
        Ok((requests, alive))
    }

    /// Carry `request` out on `compositor`, and answer it.
    fn answer(
        &self,
        mut compositor: PyRefMut<'_, local::Compositor>,
        request: PyRef<'_, HostRequest>,
    ) {
        let seq = request.seq;
        match request.request {
            Request::Pause => return self.pause(seq),
            Request::Adopt => return self.adopt(&compositor.inner, seq),
            _ => {}
        }
        let epoch = lock(&self.gate).epoch;
        match carry_out(
            &mut compositor.inner,
            &self.encoders,
            request.request.clone(),
        ) {
            Outcome::Now(result) => Self::reply(&self.sender, &self.gate, epoch, seq, result),
            Outcome::Later(work) => {
                let (sender, gate) = (self.sender.clone(), self.gate.clone());
                pyo3_async_runtimes::tokio::get_runtime().spawn_blocking(move || {
                    Self::reply(&sender, &gate, epoch, seq, work());
                });
            }
        }
    }

    /// Run `compositor.dispatch()` and send the parent what happened.
    fn forward(&self, mut compositor: PyRefMut<'_, local::Compositor>) -> PyResult<()> {
        let events = compositor.inner.dispatch().map_err(py_err)?;
        let mut gate = lock(&self.gate);
        if let Some(held) = &mut gate.held {
            held.extend(events.into_iter().filter(outlives_a_pause));
            return Ok(());
        }
        for event in events {
            self.sender.send(Message::Event(event)).map_err(py_err)?;
        }
        Ok(())
    }
}
