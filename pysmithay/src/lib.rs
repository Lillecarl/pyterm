//! A headless Wayland compositor, driven from Python.
//!
//! Python owns the event loop. It waits for either file descriptor in
//! `fds()` to become readable and then calls `dispatch()`, which accepts
//! new clients, runs their requests and returns what happened. Nothing
//! here blocks or spawns a thread.
//!
//! A window's pixels are copied out of the client's shm buffer on commit,
//! and the buffer is released at once, so a client never waits on Python
//! to reuse it.

use std::os::fd::{AsFd, AsRawFd};
use std::sync::Arc;

use pyo3::exceptions::{PyKeyError, PyOSError};
use pyo3::prelude::*;
use pyo3::types::PyBytes;
use smithay::backend::input::{ButtonState, KeyState};
use smithay::input::keyboard::{FilterResult, KeyboardHandle, XkbConfig};
use smithay::input::pointer::{ButtonEvent, MotionEvent, PointerHandle};
use smithay::input::{Seat, SeatHandler, SeatState};
use smithay::output::{Mode, Output, PhysicalProperties, Subpixel};
use smithay::reexports::wayland_protocols::xdg::shell::server::xdg_toplevel;
use smithay::reexports::wayland_server::backend::{ClientData, ClientId, DisconnectReason};
use smithay::reexports::wayland_server::protocol::wl_shm::Format;
use smithay::reexports::wayland_server::protocol::{wl_buffer, wl_surface::WlSurface};
use smithay::reexports::wayland_server::{Client, Display, ListeningSocket};
use smithay::utils::{SERIAL_COUNTER, Serial, Size};
use smithay::wayland::buffer::BufferHandler;
use smithay::wayland::compositor::{
    BufferAssignment, CompositorClientState, CompositorHandler, CompositorState, Damage,
    SurfaceAttributes, TraversalAction, with_states, with_surface_tree_downward,
};
use smithay::wayland::output::{OutputHandler, OutputManagerState};
use smithay::wayland::selection::SelectionHandler;
use smithay::wayland::selection::data_device::{
    ClientDndGrabHandler, DataDeviceHandler, DataDeviceState, ServerDndGrabHandler,
};
use smithay::wayland::shell::xdg::{
    PopupSurface, PositionerState, ToplevelSurface, XdgShellHandler, XdgShellState,
    XdgToplevelSurfaceData,
};
use smithay::wayland::shm::{BufferData, ShmHandler, ShmState, with_buffer_contents};
use smithay::{
    delegate_compositor, delegate_data_device, delegate_output, delegate_seat, delegate_shm,
    delegate_xdg_shell,
};

/// What one buffer held, as RGBA rows with no padding.
struct Frame {
    width: i32,
    height: i32,
    rgba: Vec<u8>,
}

struct Toplevel {
    id: u64,
    surface: ToplevelSurface,
    frame: Option<Frame>,
}

/// A rectangle in buffer pixels: x, y, width, height.
type Rect = (i32, i32, i32, i32);

enum Event {
    Toplevel(u64),
    Title(u64, String),
    AppId(u64, String),
    Commit(u64, Vec<Rect>),
    Closed(u64),
}

struct State {
    compositor_state: CompositorState,
    xdg_shell_state: XdgShellState,
    shm_state: ShmState,
    _output_manager_state: OutputManagerState,
    seat_state: SeatState<State>,
    data_device_state: DataDeviceState,
    toplevels: Vec<Toplevel>,
    next_id: u64,
    events: Vec<Event>,
}

// A clipboard nobody reads yet. Programs such as foot refuse to start
// without the global.
impl SelectionHandler for State {
    type SelectionUserData = ();
}

impl DataDeviceHandler for State {
    fn data_device_state(&self) -> &DataDeviceState {
        &self.data_device_state
    }
}

impl ClientDndGrabHandler for State {}
impl ServerDndGrabHandler for State {}

impl SeatHandler for State {
    type KeyboardFocus = WlSurface;
    type PointerFocus = WlSurface;
    type TouchFocus = WlSurface;

    fn seat_state(&mut self) -> &mut SeatState<Self> {
        &mut self.seat_state
    }
}

impl State {
    fn toplevel_of(&mut self, surface: &WlSurface) -> Option<&mut Toplevel> {
        self.toplevels
            .iter_mut()
            .find(|toplevel| toplevel.surface.wl_surface() == surface)
    }

    fn id_of(&self, surface: &ToplevelSurface) -> Option<u64> {
        self.toplevels
            .iter()
            .find(|toplevel| &toplevel.surface == surface)
            .map(|toplevel| toplevel.id)
    }
}

#[derive(Default)]
struct ClientState {
    compositor_state: CompositorClientState,
}

impl ClientData for ClientState {
    fn initialized(&self, _client_id: ClientId) {}
    fn disconnected(&self, _client_id: ClientId, _reason: DisconnectReason) {}
}

impl CompositorHandler for State {
    fn compositor_state(&mut self) -> &mut CompositorState {
        &mut self.compositor_state
    }

    fn client_compositor_state<'a>(&self, client: &'a Client) -> &'a CompositorClientState {
        &client.get_data::<ClientState>().unwrap().compositor_state
    }

    fn commit(&mut self, surface: &WlSurface) {
        let Some(toplevel) = self.toplevel_of(surface) else {
            return;
        };
        // xdg-shell: the first commit carries no buffer, and the client
        // waits for this configure before it draws.
        if !toplevel.surface.is_initial_configure_sent() {
            toplevel.surface.send_configure();
            return;
        }

        let (assignment, scale, damage) = with_states(surface, |states| {
            let mut guard = states.cached_state.get::<SurfaceAttributes>();
            let attributes = guard.current();
            (
                attributes.buffer.take(),
                attributes.buffer_scale,
                std::mem::take(&mut attributes.damage),
            )
        });
        let id = toplevel.id;
        let damaged = match assignment {
            None => return,
            Some(BufferAssignment::Removed) => {
                toplevel.frame = None;
                vec![]
            }
            Some(BufferAssignment::NewBuffer(buffer)) => {
                let copied = with_buffer_contents(&buffer, |pointer, length, data| {
                    // SAFETY: smithay maps the pool for the length it
                    // hands over, and holds it mapped for this call.
                    let pool = unsafe { std::slice::from_raw_parts(pointer, length) };
                    rgba_of(pool, data)
                });
                buffer.release();
                let Ok(Some(frame)) = copied else {
                    return;
                };
                let resized = toplevel
                    .frame
                    .as_ref()
                    .is_none_or(|old| (old.width, old.height) != (frame.width, frame.height));
                let damaged = if resized {
                    vec![(0, 0, frame.width, frame.height)]
                } else {
                    damage
                        .iter()
                        .filter_map(|one| clipped(one, scale, frame.width, frame.height))
                        .collect()
                };
                toplevel.frame = Some(frame);
                damaged
            }
        };
        self.events.push(Event::Commit(id, damaged));
    }
}

/// One damage rectangle in buffer pixels, inside the buffer, or none.
fn clipped(damage: &Damage, scale: i32, width: i32, height: i32) -> Option<Rect> {
    let (x, y, w, h) = match damage {
        Damage::Buffer(rect) => (rect.loc.x, rect.loc.y, rect.size.w, rect.size.h),
        Damage::Surface(rect) => (
            rect.loc.x.saturating_mul(scale),
            rect.loc.y.saturating_mul(scale),
            rect.size.w.saturating_mul(scale),
            rect.size.h.saturating_mul(scale),
        ),
    };
    let left = x.clamp(0, width);
    let top = y.clamp(0, height);
    let right = x.saturating_add(w).clamp(0, width);
    let bottom = y.saturating_add(h).clamp(0, height);
    (right > left && bottom > top).then_some((left, top, right - left, bottom - top))
}

/// The buffer's pixels as RGBA, or none for a format or a size that
/// does not fit the pool.
///
/// wl_shm's two mandatory formats are the only ones advertised. Both are
/// little-endian words, so the bytes are B, G, R, A.
fn rgba_of(pool: &[u8], data: BufferData) -> Option<Frame> {
    let opaque = match data.format {
        Format::Argb8888 => false,
        Format::Xrgb8888 => true,
        _ => return None,
    };
    let width = usize::try_from(data.width).ok()?;
    let height = usize::try_from(data.height).ok()?;
    let stride = usize::try_from(data.stride).ok()?;
    let offset = usize::try_from(data.offset).ok()?;
    if stride < width * 4 || height == 0 {
        return None;
    }
    let end = offset.checked_add(stride.checked_mul(height - 1)?.checked_add(width * 4)?)?;
    if end > pool.len() {
        return None;
    }

    let mut rgba = Vec::with_capacity(width * height * 4);
    for row in pool[offset..end].chunks(stride) {
        for pixel in row[..width * 4].chunks_exact(4) {
            let alpha = if opaque { 0xff } else { pixel[3] };
            rgba.extend_from_slice(&[pixel[2], pixel[1], pixel[0], alpha]);
        }
    }
    Some(Frame {
        width: data.width,
        height: data.height,
        rgba,
    })
}

impl BufferHandler for State {
    fn buffer_destroyed(&mut self, _buffer: &wl_buffer::WlBuffer) {}
}

impl ShmHandler for State {
    fn shm_state(&self) -> &ShmState {
        &self.shm_state
    }
}

impl OutputHandler for State {}

impl XdgShellHandler for State {
    fn xdg_shell_state(&mut self) -> &mut XdgShellState {
        &mut self.xdg_shell_state
    }

    fn new_toplevel(&mut self, surface: ToplevelSurface) {
        surface.with_pending_state(|state| {
            state.states.set(xdg_toplevel::State::Activated);
        });
        let id = self.next_id;
        self.next_id += 1;
        self.toplevels.push(Toplevel {
            id,
            surface,
            frame: None,
        });
        self.events.push(Event::Toplevel(id));
    }

    fn toplevel_destroyed(&mut self, surface: ToplevelSurface) {
        if let Some(id) = self.id_of(&surface) {
            self.toplevels.retain(|toplevel| toplevel.id != id);
            self.events.push(Event::Closed(id));
        }
    }

    fn title_changed(&mut self, surface: ToplevelSurface) {
        if let Some(id) = self.id_of(&surface) {
            let title = role_string(&surface, |role| role.title.clone());
            self.events.push(Event::Title(id, title));
        }
    }

    fn app_id_changed(&mut self, surface: ToplevelSurface) {
        if let Some(id) = self.id_of(&surface) {
            let app_id = role_string(&surface, |role| role.app_id.clone());
            self.events.push(Event::AppId(id, app_id));
        }
    }

    fn new_popup(&mut self, _surface: PopupSurface, _positioner: PositionerState) {}

    fn grab(
        &mut self,
        _surface: PopupSurface,
        _seat: smithay::reexports::wayland_server::protocol::wl_seat::WlSeat,
        _serial: Serial,
    ) {
    }

    fn reposition_request(
        &mut self,
        _surface: PopupSurface,
        _positioner: PositionerState,
        _token: u32,
    ) {
    }
}

fn role_string(
    surface: &ToplevelSurface,
    read: impl FnOnce(&smithay::wayland::shell::xdg::XdgToplevelSurfaceRoleAttributes) -> Option<String>,
) -> String {
    with_states(surface.wl_surface(), |states| {
        states
            .data_map
            .get::<XdgToplevelSurfaceData>()
            .and_then(|data| read(&data.lock().unwrap()))
            .unwrap_or_default()
    })
}

delegate_compositor!(State);
delegate_shm!(State);
delegate_output!(State);
delegate_xdg_shell!(State);
delegate_seat!(State);
delegate_data_device!(State);

/// A Wayland compositor that draws nowhere, and hands every window's
/// pixels to Python.
#[pyclass(unsendable, module = "pysmithay")]
struct Compositor {
    display: Display<State>,
    state: State,
    listener: ListeningSocket,
    output: Output,
    _seat: Seat<State>,
    keyboard: KeyboardHandle<State>,
    pointer: PointerHandle<State>,
}

fn os_error(error: impl std::fmt::Display) -> PyErr {
    PyOSError::new_err(error.to_string())
}

impl Compositor {
    fn toplevel(&self, id: u64) -> PyResult<&Toplevel> {
        self.state
            .toplevels
            .iter()
            .find(|toplevel| toplevel.id == id)
            .ok_or_else(|| PyKeyError::new_err(id))
    }

    fn flush(&mut self) -> PyResult<()> {
        self.display.flush_clients().map_err(os_error)
    }
}

#[pymethods]
impl Compositor {
    /// Listen on `$XDG_RUNTIME_DIR/<socket_name>`, or on the first free
    /// `wayland-N` when no name is given.
    #[new]
    #[pyo3(signature = (socket_name=None, width=800, height=600))]
    fn new(socket_name: Option<&str>, width: i32, height: i32) -> PyResult<Self> {
        let display = Display::<State>::new().map_err(os_error)?;
        let handle = display.handle();
        let listener = match socket_name {
            Some(name) => ListeningSocket::bind(name),
            None => ListeningSocket::bind_auto("wayland", 1..33),
        }
        .map_err(os_error)?;

        let output = Output::new(
            "pysmithay".into(),
            PhysicalProperties {
                size: (0, 0).into(),
                subpixel: Subpixel::Unknown,
                make: "pysmithay".into(),
                model: "headless".into(),
            },
        );
        let mode = Mode {
            size: (width, height).into(),
            refresh: 60_000,
        };
        output.change_current_state(Some(mode), None, None, Some((0, 0).into()));
        output.set_preferred(mode);
        output.create_global::<State>(&handle);

        let mut seat_state = SeatState::new();
        let mut seat = seat_state.new_wl_seat(&handle, "pysmithay");
        let keyboard = seat
            .add_keyboard(XkbConfig::default(), 600, 25)
            .map_err(os_error)?;
        let pointer = seat.add_pointer();

        let state = State {
            compositor_state: CompositorState::new::<State>(&handle),
            xdg_shell_state: XdgShellState::new::<State>(&handle),
            shm_state: ShmState::new::<State>(&handle, vec![]),
            _output_manager_state: OutputManagerState::new_with_xdg_output::<State>(&handle),
            seat_state,
            data_device_state: DataDeviceState::new::<State>(&handle),
            toplevels: Vec::new(),
            next_id: 1,
            events: Vec::new(),
        };
        Ok(Self {
            display,
            state,
            listener,
            output,
            _seat: seat,
            keyboard,
            pointer,
        })
    }

    /// Give the keyboard to this window.
    fn focus(&mut self, id: u64) -> PyResult<()> {
        let surface = self.toplevel(id)?.surface.wl_surface().clone();
        self.keyboard
            .set_focus(&mut self.state, Some(surface), SERIAL_COUNTER.next_serial());
        self.flush()
    }

    /// Press or release a key. `code` is the Linux evdev key code, as
    /// in `linux/input-event-codes.h`; the client's keymap is xkb's
    /// default, so the layout is applied on the client's side.
    fn key(&mut self, code: u32, pressed: bool, time: u32) -> PyResult<()> {
        let state = if pressed {
            KeyState::Pressed
        } else {
            KeyState::Released
        };
        // xkb numbers keys from 8 above evdev.
        self.keyboard.input::<(), _>(
            &mut self.state,
            (code + 8).into(),
            state,
            SERIAL_COUNTER.next_serial(),
            time,
            |_, _, _| FilterResult::Forward,
        );
        self.flush()
    }

    /// Move the pointer to `(x, y)` in the window's surface pixels.
    fn pointer_motion(&mut self, id: u64, x: f64, y: f64, time: u32) -> PyResult<()> {
        let surface = self.toplevel(id)?.surface.wl_surface().clone();
        // Every window sits at the origin: Python places it, not this.
        self.pointer.motion(
            &mut self.state,
            Some((surface, (0.0, 0.0).into())),
            &MotionEvent {
                location: (x, y).into(),
                serial: SERIAL_COUNTER.next_serial(),
                time,
            },
        );
        self.pointer.frame(&mut self.state);
        self.flush()
    }

    /// Press or release a pointer button, as an evdev code: `BTN_LEFT`
    /// is 0x110.
    fn pointer_button(&mut self, button: u32, pressed: bool, time: u32) -> PyResult<()> {
        let state = if pressed {
            ButtonState::Pressed
        } else {
            ButtonState::Released
        };
        self.pointer.button(
            &mut self.state,
            &ButtonEvent {
                serial: SERIAL_COUNTER.next_serial(),
                time,
                button,
                state,
            },
        );
        self.pointer.frame(&mut self.state);
        self.flush()
    }

    /// The name a client puts in `WAYLAND_DISPLAY`.
    #[getter]
    fn socket_name(&self) -> Option<String> {
        self.listener
            .socket_name()
            .map(|name| name.to_string_lossy().into_owned())
    }

    /// The listening socket and the display: wait on both for reading.
    fn fds(&mut self) -> (i32, i32) {
        (
            self.listener.as_raw_fd(),
            self.display.backend().poll_fd().as_fd().as_raw_fd(),
        )
    }

    /// Accept waiting clients, run every request that has arrived, and
    /// return what happened, oldest first.
    ///
    /// Each event is a tuple: `("toplevel", id)`, `("title", id, str)`,
    /// `("app_id", id, str)`, `("commit", id, [(x, y, w, h), ...])` with
    /// the damage in buffer pixels, or `("closed", id)`.
    fn dispatch(&mut self, py: Python<'_>) -> PyResult<Vec<Py<PyAny>>> {
        while let Some(stream) = self.listener.accept().map_err(os_error)? {
            self.display
                .handle()
                .insert_client(stream, Arc::new(ClientState::default()))
                .map_err(os_error)?;
        }
        self.display
            .dispatch_clients(&mut self.state)
            .map_err(os_error)?;
        self.flush()?;

        std::mem::take(&mut self.state.events)
            .into_iter()
            .map(|event| {
                Ok(match event {
                    Event::Toplevel(id) => ("toplevel", id).into_pyobject(py)?.into_any(),
                    Event::Title(id, title) => ("title", id, title).into_pyobject(py)?.into_any(),
                    Event::AppId(id, app_id) => {
                        ("app_id", id, app_id).into_pyobject(py)?.into_any()
                    }
                    Event::Commit(id, damage) => {
                        ("commit", id, damage).into_pyobject(py)?.into_any()
                    }
                    Event::Closed(id) => ("closed", id).into_pyobject(py)?.into_any(),
                }
                .unbind())
            })
            .collect()
    }

    /// The window's last buffer as `(width, height, rgba)`, or None
    /// before it has drawn.
    fn frame<'py>(
        &self,
        py: Python<'py>,
        id: u64,
    ) -> PyResult<Option<(i32, i32, Bound<'py, PyBytes>)>> {
        Ok(self
            .toplevel(id)?
            .frame
            .as_ref()
            .map(|frame| (frame.width, frame.height, PyBytes::new(py, &frame.rgba))))
    }

    /// Ask the window to be this size, in surface pixels.
    fn configure(&mut self, id: u64, width: i32, height: i32) -> PyResult<()> {
        let surface = self.toplevel(id)?.surface.clone();
        surface.with_pending_state(|state| {
            state.size = Some(Size::from((width, height)));
        });
        if surface.is_initial_configure_sent() {
            surface.send_pending_configure();
        }
        self.flush()
    }

    /// Ask the window to close. The client decides.
    fn close(&mut self, id: u64) -> PyResult<()> {
        self.toplevel(id)?.surface.send_close();
        self.flush()
    }

    /// Tell every window that its last frame was shown, so it may draw
    /// the next. `time` is in milliseconds, from any fixed start.
    fn frame_done(&mut self, time: u32) -> PyResult<()> {
        for toplevel in &self.state.toplevels {
            with_surface_tree_downward(
                toplevel.surface.wl_surface(),
                (),
                |_, _, &()| TraversalAction::DoChildren(()),
                |_, states, &()| {
                    for callback in states
                        .cached_state
                        .get::<SurfaceAttributes>()
                        .current()
                        .frame_callbacks
                        .drain(..)
                    {
                        callback.done(time);
                    }
                },
                |_, _, &()| true,
            );
        }
        self.flush()
    }

    /// The ids of the windows that are open, oldest first.
    fn toplevels(&self) -> Vec<u64> {
        self.state
            .toplevels
            .iter()
            .map(|toplevel| toplevel.id)
            .collect()
    }

    /// The output's size in pixels, which a client reads as its screen.
    #[getter]
    fn output_size(&self) -> Option<(i32, i32)> {
        self.output
            .current_mode()
            .map(|mode| (mode.size.w, mode.size.h))
    }
}

#[pymodule]
fn _native(module: &Bound<'_, PyModule>) -> PyResult<()> {
    module.add_class::<Compositor>()
}
