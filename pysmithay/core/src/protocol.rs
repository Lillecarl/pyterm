//! How a compositor in a child process and the process that shows its
//! windows speak, over one unix stream socket. Lillecarl/pyterm#1004.
//!
//! Each message is a little-endian `u32` length and that many bytes. A
//! message that carries descriptors sends them as `SCM_RIGHTS` with its
//! first byte, so a reader takes them off a queue in message order.
//!
//! The child speaks first: `Hello`, or `Failed` when it could not bind.
//! Then the parent sends requests and the child answers each one with a
//! `seq`; a request sent with `seq` 0 wants no answer, and the child
//! drops a failure of it. Events go the other way at any time.
//!
//! `VERSION` is in `Hello`. A child outlives the build that started it,
//! so a parent speaks every version a live child may have.

use std::collections::VecDeque;
use std::io::{IoSlice, IoSliceMut, Write};
use std::mem::MaybeUninit;
use std::os::fd::{AsFd, BorrowedFd, OwnedFd};
use std::os::unix::net::UnixStream;
use std::sync::Mutex;

use rustix::net::{
    RecvAncillaryBuffer, RecvAncillaryMessage, RecvFlags, SendAncillaryBuffer,
    SendAncillaryMessage, SendFlags, recvmsg, sendmsg,
};

use crate::{Error, Event, FrameRect, Rect, Result, Target};

/// The protocol this build speaks.
pub const VERSION: u32 = 1;

/// The most descriptors one message carries.
const MOST_FDS: usize = 4;

/// What one read asks for. A 1080p frame is 8 MB; it takes a few reads.
const READ_CHUNK: usize = 1 << 20;

/// What the parent asks.
#[derive(Debug, Clone, PartialEq)]
pub enum Request {
    SetSelection {
        target: Target,
        offers: Vec<(String, Option<Vec<u8>>)>,
    },
    ClearSelection {
        target: Target,
    },
    RequestSelection {
        target: Target,
        mime_type: String,
    },
    Focus {
        id: u64,
    },
    Key {
        code: u32,
        pressed: bool,
        time: u32,
    },
    CommitText {
        text: String,
    },
    PointerMotion {
        id: u64,
        x: f64,
        y: f64,
        time: u32,
    },
    PointerLeave {
        id: u64,
        time: u32,
    },
    PointerScroll {
        steps: i32,
        time: u32,
        horizontal: bool,
    },
    PointerScrollSmooth {
        id: u64,
        pixels: f64,
        time: u32,
        horizontal: bool,
    },
    PointerButton {
        button: u32,
        pressed: bool,
        time: u32,
    },
    Connect,
    Configure {
        id: u64,
        width: i32,
        height: i32,
        scale: f64,
    },
    Close {
        id: u64,
    },
    FrameDone {
        id: u64,
        time: u32,
    },
    WantsFrame {
        id: u64,
    },
    Toplevels,
    Frame {
        id: u64,
    },
    KittyUpdate {
        id: u64,
        image_id: u32,
        since: Option<u64>,
    },
    FrameRects {
        id: u64,
        since: Option<u64>,
    },
    /// The next frame of the parent's encoder `encoder`, which the child
    /// makes on first use.
    Vp9Frame {
        id: u64,
        encoder: u64,
    },
    DropEncoder {
        encoder: u64,
    },
}

/// What the child answers.
#[derive(Debug)]
pub enum Answer {
    Unit,
    Bool(bool),
    Ids(Vec<u64>),
    Fd(OwnedFd),
    Connected(u64, OwnedFd),
    Frame(crate::Frame),
    Kitty(crate::KittyUpdate),
    Rects(crate::FrameRects),
    Video(crate::VideoFrame),
}

/// One message, either way.
#[derive(Debug)]
pub enum Message {
    /// The child listens on `socket_name`, with this output.
    Hello {
        version: u32,
        socket_name: String,
        output: Option<(i32, i32)>,
    },
    /// The child could not start its compositor.
    Failed(Error),
    Request {
        seq: u64,
        request: Request,
    },
    Reply {
        seq: u64,
        result: Result<Answer>,
    },
    Event(Event),
}

impl std::fmt::Debug for Event {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        match self {
            Self::Toplevel(id, tag) => write!(f, "Toplevel({id}, {tag})"),
            Self::Title(id, title) => write!(f, "Title({id}, {title:?})"),
            Self::AppId(id, app_id) => write!(f, "AppId({id}, {app_id:?})"),
            Self::Commit(id, damage) => write!(f, "Commit({id}, {damage:?})"),
            Self::Closed(id) => write!(f, "Closed({id})"),
            Self::Pointer(id, name) => write!(f, "Pointer({id}, {name:?})"),
            Self::Selection(target, types) => write!(f, "Selection({target:?}, {types:?})"),
            Self::Send(target, mime_type, _) => write!(f, "Send({target:?}, {mime_type:?})"),
        }
    }
}

// ----------------------------------------------------------------------
// The codec.

struct Writer {
    bytes: Vec<u8>,
    fds: Vec<OwnedFd>,
}

impl Writer {
    fn new() -> Self {
        // The length goes here once the body is written.
        Self {
            bytes: vec![0; 4],
            fds: Vec::new(),
        }
    }

    fn u8(&mut self, value: u8) {
        self.bytes.push(value);
    }

    fn bool(&mut self, value: bool) {
        self.u8(u8::from(value));
    }

    fn u32(&mut self, value: u32) {
        self.bytes.extend_from_slice(&value.to_le_bytes());
    }

    fn i32(&mut self, value: i32) {
        self.bytes.extend_from_slice(&value.to_le_bytes());
    }

    fn u64(&mut self, value: u64) {
        self.bytes.extend_from_slice(&value.to_le_bytes());
    }

    fn f64(&mut self, value: f64) {
        self.bytes.extend_from_slice(&value.to_le_bytes());
    }

    fn len(&mut self, len: usize) {
        self.u32(u32::try_from(len).expect("a message part under 4 GiB"));
    }

    fn bytes(&mut self, value: &[u8]) {
        self.len(value.len());
        self.bytes.extend_from_slice(value);
    }

    fn str(&mut self, value: &str) {
        self.bytes(value.as_bytes());
    }

    fn opt_u64(&mut self, value: Option<u64>) {
        self.bool(value.is_some());
        if let Some(value) = value {
            self.u64(value);
        }
    }

    fn target(&mut self, target: Target) {
        self.u8(match target {
            Target::Clipboard => 0,
            Target::Primary => 1,
        });
    }

    fn rect(&mut self, (x, y, w, h): Rect) {
        self.i32(x);
        self.i32(y);
        self.i32(w);
        self.i32(h);
    }

    fn rects(&mut self, rects: &[Rect]) {
        self.len(rects.len());
        for &rect in rects {
            self.rect(rect);
        }
    }

    fn strings(&mut self, values: &[String]) {
        self.len(values.len());
        for value in values {
            self.str(value);
        }
    }

    fn fd(&mut self, fd: OwnedFd) {
        self.fds.push(fd);
    }

    fn error(&mut self, error: &Error) {
        match error {
            Error::NoWindow(id) => {
                self.u8(0);
                self.u64(*id);
            }
            Error::Closed => self.u8(1),
            Error::Os(text) => {
                self.u8(2);
                self.str(text);
            }
            Error::Value(text) => {
                self.u8(3);
                self.str(text);
            }
            Error::Encode(text) => {
                self.u8(4);
                self.str(text);
            }
        }
    }

    fn finish(mut self) -> (Vec<u8>, Vec<OwnedFd>) {
        let body = u32::try_from(self.bytes.len() - 4).expect("a message under 4 GiB");
        self.bytes[..4].copy_from_slice(&body.to_le_bytes());
        (self.bytes, self.fds)
    }
}

struct Reader<'a> {
    bytes: &'a [u8],
    fds: &'a mut VecDeque<OwnedFd>,
}

fn malformed(what: &str) -> Error {
    Error::Value(format!("a malformed message: {what}"))
}

impl Reader<'_> {
    fn take(&mut self, n: usize) -> Result<&[u8]> {
        if self.bytes.len() < n {
            return Err(malformed("it ends early"));
        }
        let (head, rest) = self.bytes.split_at(n);
        self.bytes = rest;
        Ok(head)
    }

    fn array<const N: usize>(&mut self) -> Result<[u8; N]> {
        Ok(self.take(N)?.try_into().expect("took N"))
    }

    fn u8(&mut self) -> Result<u8> {
        Ok(self.take(1)?[0])
    }

    fn bool(&mut self) -> Result<bool> {
        Ok(self.u8()? != 0)
    }

    fn u32(&mut self) -> Result<u32> {
        Ok(u32::from_le_bytes(self.array()?))
    }

    fn i32(&mut self) -> Result<i32> {
        Ok(i32::from_le_bytes(self.array()?))
    }

    fn u64(&mut self) -> Result<u64> {
        Ok(u64::from_le_bytes(self.array()?))
    }

    fn f64(&mut self) -> Result<f64> {
        Ok(f64::from_le_bytes(self.array()?))
    }

    fn len(&mut self) -> Result<usize> {
        Ok(self.u32()? as usize)
    }

    fn bytes(&mut self) -> Result<Vec<u8>> {
        let len = self.len()?;
        Ok(self.take(len)?.to_vec())
    }

    fn str(&mut self) -> Result<String> {
        String::from_utf8(self.bytes()?).map_err(|_| malformed("a string that is not UTF-8"))
    }

    fn opt_u64(&mut self) -> Result<Option<u64>> {
        Ok(if self.bool()? {
            Some(self.u64()?)
        } else {
            None
        })
    }

    fn target(&mut self) -> Result<Target> {
        match self.u8()? {
            0 => Ok(Target::Clipboard),
            1 => Ok(Target::Primary),
            _ => Err(malformed("a selection that is neither")),
        }
    }

    fn rect(&mut self) -> Result<Rect> {
        Ok((self.i32()?, self.i32()?, self.i32()?, self.i32()?))
    }

    fn rects(&mut self) -> Result<Vec<Rect>> {
        let len = self.len()?;
        (0..len).map(|_| self.rect()).collect()
    }

    fn strings(&mut self) -> Result<Vec<String>> {
        let len = self.len()?;
        (0..len).map(|_| self.str()).collect()
    }

    fn fd(&mut self) -> Result<OwnedFd> {
        self.fds
            .pop_front()
            .ok_or_else(|| malformed("a descriptor that did not come"))
    }

    fn error(&mut self) -> Result<Error> {
        Ok(match self.u8()? {
            0 => Error::NoWindow(self.u64()?),
            1 => Error::Closed,
            2 => Error::Os(self.str()?),
            3 => Error::Value(self.str()?),
            4 => Error::Encode(self.str()?),
            _ => return Err(malformed("an unknown error")),
        })
    }
}

fn write_request(out: &mut Writer, request: &Request) {
    match request {
        Request::SetSelection { target, offers } => {
            out.u8(0);
            out.target(*target);
            out.len(offers.len());
            for (mime_type, data) in offers {
                out.str(mime_type);
                out.bool(data.is_some());
                if let Some(data) = data {
                    out.bytes(data);
                }
            }
        }
        Request::ClearSelection { target } => {
            out.u8(1);
            out.target(*target);
        }
        Request::RequestSelection { target, mime_type } => {
            out.u8(2);
            out.target(*target);
            out.str(mime_type);
        }
        Request::Focus { id } => {
            out.u8(3);
            out.u64(*id);
        }
        Request::Key {
            code,
            pressed,
            time,
        } => {
            out.u8(4);
            out.u32(*code);
            out.bool(*pressed);
            out.u32(*time);
        }
        Request::CommitText { text } => {
            out.u8(5);
            out.str(text);
        }
        Request::PointerMotion { id, x, y, time } => {
            out.u8(6);
            out.u64(*id);
            out.f64(*x);
            out.f64(*y);
            out.u32(*time);
        }
        Request::PointerLeave { id, time } => {
            out.u8(7);
            out.u64(*id);
            out.u32(*time);
        }
        Request::PointerScroll {
            steps,
            time,
            horizontal,
        } => {
            out.u8(8);
            out.i32(*steps);
            out.u32(*time);
            out.bool(*horizontal);
        }
        Request::PointerScrollSmooth {
            id,
            pixels,
            time,
            horizontal,
        } => {
            out.u8(9);
            out.u64(*id);
            out.f64(*pixels);
            out.u32(*time);
            out.bool(*horizontal);
        }
        Request::PointerButton {
            button,
            pressed,
            time,
        } => {
            out.u8(10);
            out.u32(*button);
            out.bool(*pressed);
            out.u32(*time);
        }
        Request::Connect => out.u8(11),
        Request::Configure {
            id,
            width,
            height,
            scale,
        } => {
            out.u8(12);
            out.u64(*id);
            out.i32(*width);
            out.i32(*height);
            out.f64(*scale);
        }
        Request::Close { id } => {
            out.u8(13);
            out.u64(*id);
        }
        Request::FrameDone { id, time } => {
            out.u8(14);
            out.u64(*id);
            out.u32(*time);
        }
        Request::WantsFrame { id } => {
            out.u8(15);
            out.u64(*id);
        }
        Request::Toplevels => out.u8(16),
        Request::Frame { id } => {
            out.u8(17);
            out.u64(*id);
        }
        Request::KittyUpdate {
            id,
            image_id,
            since,
        } => {
            out.u8(18);
            out.u64(*id);
            out.u32(*image_id);
            out.opt_u64(*since);
        }
        Request::FrameRects { id, since } => {
            out.u8(19);
            out.u64(*id);
            out.opt_u64(*since);
        }
        Request::Vp9Frame { id, encoder } => {
            out.u8(20);
            out.u64(*id);
            out.u64(*encoder);
        }
        Request::DropEncoder { encoder } => {
            out.u8(21);
            out.u64(*encoder);
        }
    }
}

fn read_request(input: &mut Reader) -> Result<Request> {
    Ok(match input.u8()? {
        0 => {
            let target = input.target()?;
            let len = input.len()?;
            let offers = (0..len)
                .map(|_| {
                    let mime_type = input.str()?;
                    let data = if input.bool()? {
                        Some(input.bytes()?)
                    } else {
                        None
                    };
                    Ok((mime_type, data))
                })
                .collect::<Result<_>>()?;
            Request::SetSelection { target, offers }
        }
        1 => Request::ClearSelection {
            target: input.target()?,
        },
        2 => Request::RequestSelection {
            target: input.target()?,
            mime_type: input.str()?,
        },
        3 => Request::Focus { id: input.u64()? },
        4 => Request::Key {
            code: input.u32()?,
            pressed: input.bool()?,
            time: input.u32()?,
        },
        5 => Request::CommitText { text: input.str()? },
        6 => Request::PointerMotion {
            id: input.u64()?,
            x: input.f64()?,
            y: input.f64()?,
            time: input.u32()?,
        },
        7 => Request::PointerLeave {
            id: input.u64()?,
            time: input.u32()?,
        },
        8 => Request::PointerScroll {
            steps: input.i32()?,
            time: input.u32()?,
            horizontal: input.bool()?,
        },
        9 => Request::PointerScrollSmooth {
            id: input.u64()?,
            pixels: input.f64()?,
            time: input.u32()?,
            horizontal: input.bool()?,
        },
        10 => Request::PointerButton {
            button: input.u32()?,
            pressed: input.bool()?,
            time: input.u32()?,
        },
        11 => Request::Connect,
        12 => Request::Configure {
            id: input.u64()?,
            width: input.i32()?,
            height: input.i32()?,
            scale: input.f64()?,
        },
        13 => Request::Close { id: input.u64()? },
        14 => Request::FrameDone {
            id: input.u64()?,
            time: input.u32()?,
        },
        15 => Request::WantsFrame { id: input.u64()? },
        16 => Request::Toplevels,
        17 => Request::Frame { id: input.u64()? },
        18 => Request::KittyUpdate {
            id: input.u64()?,
            image_id: input.u32()?,
            since: input.opt_u64()?,
        },
        19 => Request::FrameRects {
            id: input.u64()?,
            since: input.opt_u64()?,
        },
        20 => Request::Vp9Frame {
            id: input.u64()?,
            encoder: input.u64()?,
        },
        21 => Request::DropEncoder {
            encoder: input.u64()?,
        },
        _ => return Err(malformed("an unknown request")),
    })
}

fn write_answer(out: &mut Writer, answer: Answer) {
    match answer {
        Answer::Unit => out.u8(0),
        Answer::Bool(value) => {
            out.u8(1);
            out.bool(value);
        }
        Answer::Ids(ids) => {
            out.u8(2);
            out.len(ids.len());
            for id in ids {
                out.u64(id);
            }
        }
        Answer::Fd(fd) => {
            out.u8(3);
            out.fd(fd);
        }
        Answer::Connected(tag, fd) => {
            out.u8(4);
            out.u64(tag);
            out.fd(fd);
        }
        Answer::Frame(frame) => {
            out.u8(5);
            out.bool(frame.is_some());
            if let Some((width, height, rgba)) = frame {
                out.i32(width);
                out.i32(height);
                out.bytes(&rgba);
            }
        }
        Answer::Kitty((serial, commands, whole)) => {
            out.u8(6);
            out.u64(serial);
            out.bool(commands.is_some());
            if let Some(commands) = commands {
                out.str(&commands);
            }
            out.bool(whole);
        }
        Answer::Rects(rects) => {
            out.u8(7);
            out.bool(rects.is_some());
            if let Some((serial, whole, width, height, rects)) = rects {
                out.u64(serial);
                out.bool(whole);
                out.i32(width);
                out.i32(height);
                out.len(rects.len());
                for (x, y, w, h, pixels) in rects {
                    out.rect((x, y, w, h));
                    out.bytes(&pixels);
                }
            }
        }
        Answer::Video(frame) => {
            out.u8(8);
            out.bool(frame.is_some());
            if let Some((serial, keyframe, width, height, data, rects)) = frame {
                out.u64(serial);
                out.bool(keyframe);
                out.i32(width);
                out.i32(height);
                out.bytes(&data);
                out.rects(&rects);
            }
        }
    }
}

fn read_answer(input: &mut Reader) -> Result<Answer> {
    Ok(match input.u8()? {
        0 => Answer::Unit,
        1 => Answer::Bool(input.bool()?),
        2 => {
            let len = input.len()?;
            Answer::Ids((0..len).map(|_| input.u64()).collect::<Result<_>>()?)
        }
        3 => Answer::Fd(input.fd()?),
        4 => Answer::Connected(input.u64()?, input.fd()?),
        5 => Answer::Frame(if input.bool()? {
            Some((input.i32()?, input.i32()?, input.bytes()?))
        } else {
            None
        }),
        6 => {
            let serial = input.u64()?;
            let commands = if input.bool()? {
                Some(input.str()?)
            } else {
                None
            };
            Answer::Kitty((serial, commands, input.bool()?))
        }
        7 => Answer::Rects(if input.bool()? {
            let serial = input.u64()?;
            let whole = input.bool()?;
            let width = input.i32()?;
            let height = input.i32()?;
            let len = input.len()?;
            let rects = (0..len)
                .map(|_| {
                    let (x, y, w, h) = input.rect()?;
                    Ok((x, y, w, h, input.bytes()?))
                })
                .collect::<Result<Vec<FrameRect>>>()?;
            Some((serial, whole, width, height, rects))
        } else {
            None
        }),
        8 => Answer::Video(if input.bool()? {
            Some((
                input.u64()?,
                input.bool()?,
                input.i32()?,
                input.i32()?,
                input.bytes()?,
                input.rects()?,
            ))
        } else {
            None
        }),
        _ => return Err(malformed("an unknown answer")),
    })
}

fn write_event(out: &mut Writer, event: Event) {
    match event {
        Event::Toplevel(id, tag) => {
            out.u8(0);
            out.u64(id);
            out.u64(tag);
        }
        Event::Title(id, title) => {
            out.u8(1);
            out.u64(id);
            out.str(&title);
        }
        Event::AppId(id, app_id) => {
            out.u8(2);
            out.u64(id);
            out.str(&app_id);
        }
        Event::Commit(id, damage) => {
            out.u8(3);
            out.u64(id);
            out.rects(&damage);
        }
        Event::Closed(id) => {
            out.u8(4);
            out.u64(id);
        }
        Event::Pointer(id, name) => {
            out.u8(5);
            out.u64(id);
            out.str(&name);
        }
        Event::Selection(target, mime_types) => {
            out.u8(6);
            out.target(target);
            out.strings(&mime_types);
        }
        Event::Send(target, mime_type, fd) => {
            out.u8(7);
            out.target(target);
            out.str(&mime_type);
            out.fd(fd);
        }
    }
}

fn read_event(input: &mut Reader) -> Result<Event> {
    Ok(match input.u8()? {
        0 => Event::Toplevel(input.u64()?, input.u64()?),
        1 => Event::Title(input.u64()?, input.str()?),
        2 => Event::AppId(input.u64()?, input.str()?),
        3 => Event::Commit(input.u64()?, input.rects()?),
        4 => Event::Closed(input.u64()?),
        5 => Event::Pointer(input.u64()?, input.str()?),
        6 => Event::Selection(input.target()?, input.strings()?),
        7 => Event::Send(input.target()?, input.str()?, input.fd()?),
        _ => return Err(malformed("an unknown event")),
    })
}

/// `message` as the bytes and descriptors that carry it.
pub fn encode(message: Message) -> (Vec<u8>, Vec<OwnedFd>) {
    let mut out = Writer::new();
    match message {
        Message::Hello {
            version,
            socket_name,
            output,
        } => {
            out.u8(0);
            out.u32(version);
            out.str(&socket_name);
            out.bool(output.is_some());
            if let Some((width, height)) = output {
                out.i32(width);
                out.i32(height);
            }
        }
        Message::Failed(error) => {
            out.u8(1);
            out.error(&error);
        }
        Message::Request { seq, request } => {
            out.u8(2);
            out.u64(seq);
            write_request(&mut out, &request);
        }
        Message::Reply { seq, result } => {
            out.u8(3);
            out.u64(seq);
            match result {
                Ok(answer) => {
                    out.bool(true);
                    write_answer(&mut out, answer);
                }
                Err(error) => {
                    out.bool(false);
                    out.error(&error);
                }
            }
        }
        Message::Event(event) => {
            out.u8(4);
            write_event(&mut out, event);
        }
    }
    out.finish()
}

/// The message in `body`, taking its descriptors off `fds`.
pub fn decode(body: &[u8], fds: &mut VecDeque<OwnedFd>) -> Result<Message> {
    let mut input = Reader { bytes: body, fds };
    let message = match input.u8()? {
        0 => {
            let version = input.u32()?;
            let socket_name = input.str()?;
            let output = if input.bool()? {
                Some((input.i32()?, input.i32()?))
            } else {
                None
            };
            Message::Hello {
                version,
                socket_name,
                output,
            }
        }
        1 => Message::Failed(input.error()?),
        2 => Message::Request {
            seq: input.u64()?,
            request: read_request(&mut input)?,
        },
        3 => {
            let seq = input.u64()?;
            let result = if input.bool()? {
                Ok(read_answer(&mut input)?)
            } else {
                Err(input.error()?)
            };
            Message::Reply { seq, result }
        }
        4 => Message::Event(read_event(&mut input)?),
        _ => return Err(malformed("an unknown message")),
    };
    if !input.bytes.is_empty() {
        return Err(malformed("bytes after its end"));
    }
    Ok(message)
}

// ----------------------------------------------------------------------
// The socket.

fn os(error: impl std::fmt::Display) -> Error {
    Error::Os(error.to_string())
}

/// The writing end, shared by every thread that answers: a message goes
/// out whole, under the lock.
pub struct Sender {
    stream: Mutex<UnixStream>,
}

impl Sender {
    pub fn new(stream: UnixStream) -> Self {
        Self {
            stream: Mutex::new(stream),
        }
    }

    pub fn send(&self, message: Message) -> Result<()> {
        let (bytes, fds) = encode(message);
        let stream = self
            .stream
            .lock()
            .unwrap_or_else(|poisoned| poisoned.into_inner());
        let mut stream = &*stream;
        let mut sent = 0;
        if !fds.is_empty() {
            let borrowed: Vec<BorrowedFd> = fds.iter().map(AsFd::as_fd).collect();
            let mut space = [MaybeUninit::uninit(); rustix::cmsg_space!(ScmRights(MOST_FDS))];
            let mut control = SendAncillaryBuffer::new(&mut space);
            if !control.push(SendAncillaryMessage::ScmRights(&borrowed)) {
                return Err(Error::Value("too many descriptors in one message".into()));
            }
            sent = sendmsg(
                stream,
                &[IoSlice::new(&bytes)],
                &mut control,
                SendFlags::NOSIGNAL,
            )
            .map_err(os)?;
        }
        stream.write_all(&bytes[sent..]).map_err(os)
    }
}

/// The reading end: one thread reads it.
pub struct Receiver {
    stream: UnixStream,
    /// Read into, between `start` and `end`. It only grows, so a read
    /// zeroes nothing: a pointer move costs one small read, not a fill
    /// of `READ_CHUNK`.
    buffer: Vec<u8>,
    start: usize,
    end: usize,
    fds: VecDeque<OwnedFd>,
}

impl Receiver {
    pub fn new(stream: UnixStream) -> Self {
        Self {
            stream,
            buffer: Vec::new(),
            start: 0,
            end: 0,
            fds: VecDeque::new(),
        }
    }

    /// A whole message already read, if one is.
    fn parsed(&mut self) -> Result<Option<Message>> {
        let held = &self.buffer[self.start..self.end];
        let Some(head) = held.get(..4) else {
            return Ok(None);
        };
        let len = u32::from_le_bytes(head.try_into().expect("four bytes")) as usize;
        let Some(body) = held.get(4..4 + len) else {
            return Ok(None);
        };
        let message = decode(body, &mut self.fds)?;
        self.start += 4 + len;
        if self.start == self.end {
            self.start = 0;
            self.end = 0;
        }
        Ok(Some(message))
    }

    /// Read once: false when the other end closed. Unless `wait`, true
    /// with nothing read when nothing waits. The socket itself stays
    /// blocking: the `Sender` shares it, and writes a frame whole.
    fn fill(&mut self, wait: bool) -> Result<bool> {
        if self.buffer.len() - self.end < READ_CHUNK {
            if self.start > 0 {
                self.buffer.copy_within(self.start..self.end, 0);
                self.end -= self.start;
                self.start = 0;
            }
            if self.buffer.len() - self.end < READ_CHUNK {
                self.buffer.resize(self.end + READ_CHUNK, 0);
            }
        }
        let held = self.end;
        let mut space = [MaybeUninit::uninit(); rustix::cmsg_space!(ScmRights(MOST_FDS))];
        let mut control = RecvAncillaryBuffer::new(&mut space);
        let read = recvmsg(
            &self.stream,
            &mut [IoSliceMut::new(&mut self.buffer[held..])],
            &mut control,
            if wait {
                RecvFlags::CMSG_CLOEXEC
            } else {
                RecvFlags::CMSG_CLOEXEC | RecvFlags::DONTWAIT
            },
        );
        for message in control.drain() {
            if let RecvAncillaryMessage::ScmRights(fds) = message {
                self.fds.extend(fds);
            }
        }
        match read {
            Ok(got) => {
                self.end = held + got.bytes;
                Ok(got.bytes > 0)
            }
            // Waiting, it is the socket's read timeout that ran out.
            Err(rustix::io::Errno::AGAIN) if !wait => Ok(true),
            Err(rustix::io::Errno::INTR) => Ok(true),
            Err(error) => Err(os(error)),
        }
    }

    /// The next message, waiting for it; None once the other end closed.
    pub fn receive(&mut self) -> Result<Option<Message>> {
        loop {
            if let Some(message) = self.parsed()? {
                return Ok(Some(message));
            }
            if !self.fill(true)? {
                return Ok(None);
            }
        }
    }

    /// Every message that has come, without waiting; and whether the
    /// other end is still there.
    pub fn ready(&mut self) -> Result<(Vec<Message>, bool)> {
        let mut found = Vec::new();
        loop {
            while let Some(message) = self.parsed()? {
                found.push(message);
            }
            let before = self.end - self.start;
            if !self.fill(false)? {
                return Ok((found, false));
            }
            if self.end - self.start == before {
                return Ok((found, true));
            }
        }
    }
}

impl From<std::io::Error> for Error {
    fn from(error: std::io::Error) -> Self {
        os(error)
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn round_trip(message: Message) -> Message {
        let (bytes, fds) = encode(message);
        let mut fds: VecDeque<OwnedFd> = fds.into();
        let len = u32::from_le_bytes(bytes[..4].try_into().unwrap()) as usize;
        assert_eq!(len, bytes.len() - 4);
        decode(&bytes[4..], &mut fds).unwrap()
    }

    #[test]
    fn a_request_comes_back_as_it_went() {
        let request = Request::SetSelection {
            target: Target::Primary,
            offers: vec![
                ("text/plain".into(), Some(b"hi".to_vec())),
                ("x".into(), None),
            ],
        };
        match round_trip(Message::Request {
            seq: 7,
            request: request.clone(),
        }) {
            Message::Request {
                seq: 7,
                request: back,
            } => assert_eq!(back, request),
            other => panic!("{other:?}"),
        }
    }

    #[test]
    fn a_frame_and_an_error_come_back() {
        match round_trip(Message::Reply {
            seq: 3,
            result: Ok(Answer::Video(Some((
                9,
                true,
                4,
                2,
                vec![1, 2, 3],
                vec![(0, 0, 4, 2)],
            )))),
        }) {
            Message::Reply {
                seq: 3,
                result: Ok(Answer::Video(Some((9, true, 4, 2, data, rects)))),
            } => {
                assert_eq!(data, vec![1, 2, 3]);
                assert_eq!(rects, vec![(0, 0, 4, 2)]);
            }
            other => panic!("{other:?}"),
        }
        match round_trip(Message::Reply {
            seq: 4,
            result: Err(Error::NoWindow(12)),
        }) {
            Message::Reply {
                seq: 4,
                result: Err(Error::NoWindow(12)),
            } => {}
            other => panic!("{other:?}"),
        }
    }

    #[test]
    fn a_descriptor_crosses_the_socket_with_its_message() {
        let (ours, theirs) = UnixStream::pair().unwrap();
        let (pipe, _keep) = std::io::pipe().unwrap();
        let sender = Sender::new(ours);
        sender
            .send(Message::Reply {
                seq: 1,
                result: Ok(Answer::Fd(OwnedFd::from(pipe))),
            })
            .unwrap();
        sender.send(Message::Event(Event::Closed(5))).unwrap();
        let mut receiver = Receiver::new(theirs);
        assert!(matches!(
            receiver.receive().unwrap(),
            Some(Message::Reply {
                seq: 1,
                result: Ok(Answer::Fd(_))
            })
        ));
        assert!(matches!(
            receiver.receive().unwrap(),
            Some(Message::Event(Event::Closed(5)))
        ));
        drop(sender);
        assert!(receiver.receive().unwrap().is_none());
    }

    #[test]
    fn a_frame_larger_than_a_read_comes_whole_between_small_messages() {
        let (ours, theirs) = UnixStream::pair().unwrap();
        let rgba: Vec<u8> = (0..3 * READ_CHUNK + 17).map(|at| at as u8).collect();
        let expected = rgba.clone();
        let writer = std::thread::spawn(move || {
            let sender = Sender::new(ours);
            for seq in 0..3 {
                sender.send(Message::Event(Event::Closed(seq))).unwrap();
            }
            sender
                .send(Message::Reply {
                    seq: 9,
                    result: Ok(Answer::Frame(Some((1, 1, rgba)))),
                })
                .unwrap();
            sender.send(Message::Event(Event::Closed(3))).unwrap();
        });
        let mut receiver = Receiver::new(theirs);
        for seq in 0..3 {
            assert!(
                matches!(receiver.receive().unwrap(), Some(Message::Event(Event::Closed(got))) if got == seq)
            );
        }
        match receiver.receive().unwrap() {
            Some(Message::Reply {
                seq: 9,
                result: Ok(Answer::Frame(Some((1, 1, got)))),
            }) => assert!(got == expected),
            other => panic!("{other:?}"),
        }
        assert!(matches!(
            receiver.receive().unwrap(),
            Some(Message::Event(Event::Closed(3)))
        ));
        writer.join().unwrap();
        assert!(receiver.receive().unwrap().is_none());
    }
}
