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

use std::collections::{HashMap, VecDeque};
use std::io::Write;
use std::os::fd::{AsFd, AsRawFd, IntoRawFd, OwnedFd};
use std::os::unix::net::UnixStream;
use std::path::PathBuf;
use std::sync::Arc;
use std::time::Duration;

use pyo3::exceptions::{PyKeyError, PyOSError, PyRuntimeError, PyValueError};
use pyo3::prelude::*;
use pyo3::types::PyBytes;
use smithay::backend::input::{Axis, AxisSource, ButtonState, KeyState};
use smithay::input::keyboard::{FilterResult, KeyboardHandle, XkbConfig};
use smithay::input::pointer::{
    AxisFrame, ButtonEvent, CursorImageStatus, Focus, MotionEvent, PointerHandle,
};
use smithay::input::{Seat, SeatHandler, SeatState};
use smithay::output::{Mode, Output, PhysicalProperties, Subpixel};
use smithay::backend::renderer::pixman::PixmanRenderer;
use smithay::backend::renderer::utils::on_commit_buffer_handler;
use smithay::desktop::{
    PopupKeyboardGrab, PopupKind, PopupManager, PopupPointerGrab, PopupUngrabStrategy, Window,
    WindowSurfaceType, find_popup_root_surface, get_popup_toplevel_coords,
};
use smithay::reexports::wayland_protocols::xdg::shell::server::xdg_toplevel;
use smithay::reexports::wayland_server::backend::{ClientData, ClientId, DisconnectReason};
use smithay::reexports::wayland_server::protocol::{wl_buffer, wl_surface::WlSurface};
use smithay::reexports::wayland_server::{Client, Display, ListeningSocket, Resource};
use smithay::utils::{Logical, Point, Rectangle, SERIAL_COUNTER, Serial, Size, Transform};
use smithay::wayland::buffer::BufferHandler;
use smithay::wayland::cursor_shape::CursorShapeManagerState;
use smithay::wayland::compositor::{
    CompositorClientState, CompositorHandler, CompositorState, SurfaceData, get_parent,
    send_surface_state, with_states,
};
use smithay::wayland::fractional_scale::{
    FractionalScaleHandler, FractionalScaleManagerState, with_fractional_scale,
};
use smithay::wayland::output::{OutputHandler, OutputManagerState};
use smithay::wayland::selection::data_device::{
    ClientDndGrabHandler, DataDeviceHandler, DataDeviceState, ServerDndGrabHandler,
    clear_data_device_selection, request_data_device_client_selection, set_data_device_selection,
};
use smithay::wayland::selection::primary_selection::{
    PrimarySelectionHandler, PrimarySelectionState, clear_primary_selection,
    request_primary_client_selection, set_primary_selection,
};
use smithay::wayland::selection::{
    SelectionHandler, SelectionSource, SelectionTarget, ext_data_control, wlr_data_control,
};
use smithay::reexports::wayland_protocols::xdg::decoration::zv1::server::zxdg_toplevel_decoration_v1::Mode as DecorationMode;
use smithay::wayland::shell::xdg::decoration::{XdgDecorationHandler, XdgDecorationState};
use smithay::wayland::shell::xdg::{
    PopupSurface, PositionerState, ToplevelSurface, XdgShellHandler, XdgShellState,
    XdgToplevelSurfaceData,
};
use smithay::wayland::shm::{ShmHandler, ShmState};
use smithay::wayland::tablet_manager::TabletSeatHandler;
use smithay::wayland::viewporter::ViewporterState;
use smithay::{
    delegate_compositor, delegate_cursor_shape, delegate_data_control, delegate_data_device, delegate_ext_data_control,
    delegate_fractional_scale, delegate_output, delegate_primary_selection, delegate_seat, delegate_shm,
    delegate_viewporter, delegate_xdg_decoration, delegate_xdg_shell,
};

mod canvas;
mod kitty;
mod vp9;

use canvas::Canvas;

/// How many frames of damage a window remembers. A reader further
/// behind than this gets the whole frame again.
const HISTORY: usize = 64;

struct Toplevel {
    id: u64,
    window: Window,
    /// The window drawn whole, once it has drawn anything.
    canvas: Option<Canvas>,
    /// The size Python asked for, in canvas pixels. Until it asks, the
    /// window's own.
    wanted: Option<(i32, i32)>,
    /// Canvas pixels per logical pixel: the window is configured at
    /// `wanted / scale` and drawn back up to `wanted`.
    scale: f64,
    /// A surface of the window committed since it was last drawn.
    dirty: bool,
    /// Counts the frames drawn. A reader names the last one it saw.
    serial: u64,
    /// The serial whose canvas changed size: nothing before it is an
    /// edit of the current frame.
    resized_at: u64,
    /// The damage of the recent serials, oldest first.
    history: VecDeque<(u64, Vec<Rect>)>,
}

impl Toplevel {
    fn surface(&self) -> &ToplevelSurface {
        self.window
            .toplevel()
            .expect("every window here is made from a toplevel")
    }

    /// Draw the window if a surface of it committed, and return the
    /// damage, which is empty when the commit changed no pixel; None
    /// when nothing committed.
    ///
    /// An empty commit is still news: it may carry a frame callback, and
    /// Firefox paints nothing until that is answered. Lillecarl/pymux#638.
    fn render(&mut self, renderer: &mut PixmanRenderer) -> Option<Vec<Rect>> {
        if !std::mem::take(&mut self.dirty) {
            return None;
        }
        let (width, height) = self.wanted.unwrap_or_else(|| {
            let size = self.window.geometry().size.to_f64().to_physical(self.scale);
            (size.w.round() as i32, size.h.round() as i32)
        });
        if width <= 0 || height <= 0 {
            return None;
        }
        let resized = self.canvas.as_ref().is_none_or(|canvas| {
            (canvas.width, canvas.height, canvas.scale) != (width, height, self.scale)
        });
        if resized {
            self.canvas = Some(Canvas::new(renderer, width, height, self.scale)?);
        }
        let canvas = self.canvas.as_mut()?;
        let damage = canvas.render(renderer, &self.window);
        if damage.is_empty() && !resized {
            return Some(damage);
        }
        self.serial += 1;
        if resized {
            self.resized_at = self.serial;
            self.history.clear();
        }
        self.history.push_back((self.serial, damage.clone()));
        if self.history.len() > HISTORY {
            self.history.pop_front();
        }
        Some(damage)
    }

    /// The damage since serial `since`, merged, when the frame the
    /// reader holds can be brought up to date by edits; None when it has
    /// to be sent whole: a reader that holds none, one from before a
    /// resize, or one further behind than the history.
    fn damage_since(&self, since: Option<u64>) -> Option<Vec<Rect>> {
        let since = since?;
        let covered = since >= self.resized_at
            && since < self.serial
            && self
                .history
                .front()
                .is_some_and(|&(oldest, _)| oldest <= since + 1);
        covered.then(|| {
            self.history
                .iter()
                .filter(|(at, _)| *at > since)
                .flat_map(|(_, rects)| rects.iter().copied())
                .collect()
        })
    }

    /// The canvas size in the window's own, logical pixels.
    fn logical_size(&self) -> Option<Size<i32, Logical>> {
        self.wanted
            .map(|(width, height)| logical(width, height, self.scale))
    }

    /// Tell every surface of the window, its popups and subsurfaces
    /// included, the scale to draw at. Each is told once per change.
    fn tell_scale(&self) {
        let scale = self.scale;
        self.window
            .with_surfaces(|surface, states| tell_scale(surface, states, scale));
    }
}

fn logical(width: i32, height: i32, scale: f64) -> Size<i32, Logical> {
    Size::from((
        (f64::from(width) / scale).round() as i32,
        (f64::from(height) / scale).round() as i32,
    ))
}

/// A client with `wp_fractional_scale_v1` draws at `scale` exactly. One
/// with only `wl_surface` 6 draws at the next whole number, and the
/// canvas takes it back down.
fn tell_scale(surface: &WlSurface, states: &SurfaceData, scale: f64) {
    with_fractional_scale(states, |fractional| fractional.set_preferred_scale(scale));
    send_surface_state(surface, states, scale.ceil() as i32, Transform::Normal);
}

/// A rectangle in buffer pixels: x, y, width, height.
type Rect = (i32, i32, i32, i32);

/// Pixels that go to Python as `bytes`.
struct FrameBytes(Vec<u8>);

impl<'py> IntoPyObject<'py> for FrameBytes {
    type Target = PyBytes;
    type Output = Bound<'py, PyBytes>;
    type Error = std::convert::Infallible;

    fn into_pyobject(self, py: Python<'py>) -> Result<Self::Output, Self::Error> {
        Ok(PyBytes::new(py, &self.0))
    }
}

/// One rectangle of `frame_rects`: x, y, width, height and its pixels.
type FrameRect = (i32, i32, i32, i32, FrameBytes);

/// What `vp9_frame` answers: serial, keyframe, width, height, the data,
/// and the rectangles it changed.
type VideoFrame = (u64, bool, i32, i32, FrameBytes, Vec<Rect>);

enum Event {
    /// A window, and the tag of its client's connection.
    Toplevel(u64, u64),
    Title(u64, String),
    AppId(u64, String),
    Commit(u64, Vec<Rect>),
    Closed(u64),
    /// A window asked for a pointer of this CSS name, or for one the
    /// terminal picks: "" for a hidden pointer or a picture of its own.
    Pointer(u64, String),
    /// A client set a selection, offering these mime types, or cleared
    /// it when there are none.
    Selection(SelectionTarget, Vec<String>),
    /// A client asked for a held selection that Python answers itself:
    /// write the mime type into the descriptor, then close it.
    Send(SelectionTarget, String, OwnedFd),
}

struct State {
    compositor_state: CompositorState,
    xdg_shell_state: XdgShellState,
    shm_state: ShmState,
    _output_manager_state: OutputManagerState,
    seat_state: SeatState<State>,
    data_device_state: DataDeviceState,
    primary_selection_state: PrimarySelectionState,
    wlr_data_control_state: wlr_data_control::DataControlState,
    ext_data_control_state: ext_data_control::DataControlState,
    _xdg_decoration_state: XdgDecorationState,
    /// Scaling and cropping of a surface, which mpv's software output
    /// will not run without. The renderer honours it when it draws.
    _viewporter_state: ViewporterState,
    _fractional_scale_state: FractionalScaleManagerState,
    /// `wp_cursor_shape_v1`: a pointer named, which a terminal can show.
    _cursor_shape_state: CursorShapeManagerState,
    /// The window the pointer last moved over. A pointer request names
    /// no window, and only the client under the pointer may make one.
    pointer_over: Option<u64>,
    /// The one output, which every surface is on: a client that reads
    /// its scale from `wl_output` sees it only on a surface it entered.
    output: Output,
    popups: PopupManager,
    toplevels: Vec<Toplevel>,
    next_id: u64,
    events: Vec<Event>,
}

/// A selection the compositor holds itself: each mime type and its
/// bytes, or None when Python answers each request as it comes.
type Offers = Arc<HashMap<String, Option<Vec<u8>>>>;

impl SelectionHandler for State {
    type SelectionUserData = Offers;

    fn new_selection(
        &mut self,
        target: SelectionTarget,
        source: Option<SelectionSource>,
        _seat: Seat<Self>,
    ) {
        let mime_types = source.map(|source| source.mime_types()).unwrap_or_default();
        self.events.push(Event::Selection(target, mime_types));
    }

    fn send_selection(
        &mut self,
        target: SelectionTarget,
        mime_type: String,
        fd: OwnedFd,
        _seat: Seat<Self>,
        offers: &Offers,
    ) {
        match offers.get(&mime_type) {
            Some(Some(_)) => {
                let offers = Arc::clone(offers);
                // A pipe holds 64 KiB, and the reader drains it when it
                // likes: a write on this thread could stall every client.
                std::thread::spawn(move || {
                    if let Some(Some(bytes)) = offers.get(&mime_type) {
                        let _ = std::fs::File::from(fd).write_all(bytes);
                    }
                });
            }
            Some(None) => self.events.push(Event::Send(target, mime_type, fd)),
            None => {}
        }
    }
}

impl PrimarySelectionHandler for State {
    fn primary_selection_state(&self) -> &PrimarySelectionState {
        &self.primary_selection_state
    }
}

impl wlr_data_control::DataControlHandler for State {
    fn data_control_state(&self) -> &wlr_data_control::DataControlState {
        &self.wlr_data_control_state
    }
}

impl ext_data_control::DataControlHandler for State {
    fn data_control_state(&self) -> &ext_data_control::DataControlState {
        &self.ext_data_control_state
    }
}

fn target_of(name: &str) -> PyResult<SelectionTarget> {
    match name {
        "clipboard" => Ok(SelectionTarget::Clipboard),
        "primary" => Ok(SelectionTarget::Primary),
        _ => Err(PyValueError::new_err(format!(
            "a selection is \"clipboard\" or \"primary\", not {name:?}"
        ))),
    }
}

fn name_of(target: SelectionTarget) -> &'static str {
    match target {
        SelectionTarget::Clipboard => "clipboard",
        SelectionTarget::Primary => "primary",
    }
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

    fn cursor_image(&mut self, _seat: &Seat<Self>, image: CursorImageStatus) {
        let Some(id) = self.pointer_over else {
            return;
        };
        let name = match image {
            CursorImageStatus::Named(icon) => icon.name(),
            CursorImageStatus::Hidden | CursorImageStatus::Surface(_) => "",
        };
        self.events.push(Event::Pointer(id, name.to_owned()));
    }
}

impl TabletSeatHandler for State {}

impl State {
    fn toplevel_of(&mut self, surface: &WlSurface) -> Option<&mut Toplevel> {
        self.toplevels
            .iter_mut()
            .find(|toplevel| toplevel.surface().wl_surface() == surface)
    }

    fn id_of(&self, surface: &ToplevelSurface) -> Option<u64> {
        self.toplevels
            .iter()
            .find(|toplevel| toplevel.surface() == surface)
            .map(|toplevel| toplevel.id)
    }

    /// Where a popup goes: as its positioner asks, flipped, slid or
    /// shrunk to stay inside the window it belongs to. The positioner
    /// reads rectangles relative to the parent's geometry, and the
    /// window's geometry sits at the canvas origin.
    fn popup_geometry(
        &self,
        popup: &PopupSurface,
        positioner: &PositionerState,
    ) -> Rectangle<i32, Logical> {
        let kind = PopupKind::Xdg(popup.clone());
        let size = find_popup_root_surface(&kind).ok().and_then(|root| {
            self.toplevels
                .iter()
                .find(|toplevel| toplevel.surface().wl_surface() == &root)
                .map(|toplevel| {
                    toplevel
                        .logical_size()
                        .unwrap_or_else(|| toplevel.window.geometry().size)
                })
        });
        let Some(size) = size else {
            return positioner.get_geometry();
        };
        let parent = get_popup_toplevel_coords(&kind);
        let target = Rectangle::new((-parent.x, -parent.y).into(), size);
        positioner.get_unconstrained_geometry(target)
    }

    /// The root surface of the window that shows `surface`: through
    /// subsurfaces to their parent, and through popups to the toplevel
    /// they hang from.
    fn window_root_of(&self, surface: &WlSurface) -> WlSurface {
        let mut root = surface.clone();
        while let Some(parent) = get_parent(&root) {
            root = parent;
        }
        if let Some(popup) = self.popups.find_popup(&root)
            && let Ok(toplevel) = find_popup_root_surface(&popup)
        {
            return toplevel;
        }
        root
    }
}

struct ClientState {
    compositor_state: CompositorClientState,
    /// The tag of the `connect` the client came from; 0 for the
    /// listening socket.
    origin: u64,
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

    /// A surface took new state. Its buffer goes to the renderer, which
    /// holds it until the next one and releases it then, and the window
    /// that shows it is drawn on the next `dispatch`.
    fn commit(&mut self, surface: &WlSurface) {
        on_commit_buffer_handler::<Self>(surface);
        self.popups.commit(surface);

        // xdg-shell: the first commit carries no buffer, and the client
        // waits for this configure before it draws. A popup the same.
        if let Some(toplevel) = self.toplevel_of(surface)
            && !toplevel.surface().is_initial_configure_sent()
        {
            toplevel.surface().send_configure();
        }
        if let Some(PopupKind::Xdg(popup)) = self.popups.find_popup(surface)
            && !popup.is_initial_configure_sent()
        {
            let _ = popup.send_configure();
        }

        self.output.enter(surface);
        let root = self.window_root_of(surface);
        if let Some(toplevel) = self.toplevel_of(&root) {
            toplevel.window.on_commit();
            toplevel.dirty = true;
            let scale = toplevel.scale;
            with_states(surface, |states| tell_scale(surface, states, scale));
        }
    }
}

impl FractionalScaleHandler for State {
    fn new_fractional_scale(&mut self, surface: WlSurface) {
        let root = self.window_root_of(&surface);
        if let Some(toplevel) = self.toplevel_of(&root) {
            let scale = toplevel.scale;
            with_states(&surface, |states| tell_scale(&surface, states, scale));
        }
    }
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

/// Every window is drawn without a title bar of its own: whoever shows
/// it draws the frame around it, as a pymux pane does.
impl XdgDecorationHandler for State {
    fn new_decoration(&mut self, toplevel: ToplevelSurface) {
        server_side(&toplevel);
    }

    fn request_mode(&mut self, toplevel: ToplevelSurface, _mode: DecorationMode) {
        server_side(&toplevel);
    }

    fn unset_mode(&mut self, toplevel: ToplevelSurface) {
        server_side(&toplevel);
    }
}

fn server_side(toplevel: &ToplevelSurface) {
    toplevel.with_pending_state(|state| {
        state.decoration_mode = Some(DecorationMode::ServerSide);
    });
    // Before the first configure, that configure carries it.
    if toplevel.is_initial_configure_sent() {
        toplevel.send_pending_configure();
    }
}

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
        let origin = surface
            .wl_surface()
            .client()
            .and_then(|client| client.get_data::<ClientState>().map(|data| data.origin))
            .unwrap_or(0);
        self.toplevels.push(Toplevel {
            id,
            window: Window::new_wayland_window(surface),
            canvas: None,
            wanted: None,
            scale: 1.0,
            dirty: false,
            serial: 0,
            resized_at: 0,
            history: VecDeque::new(),
        });
        self.events.push(Event::Toplevel(id, origin));
    }

    fn toplevel_destroyed(&mut self, surface: ToplevelSurface) {
        if let Some(id) = self.id_of(&surface) {
            self.toplevels.retain(|toplevel| toplevel.id != id);
            if self.pointer_over == Some(id) {
                self.pointer_over = None;
            }
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

    /// A menu or a tooltip. It goes where its positioner says, moved
    /// back inside the window when it would hang over an edge: the
    /// canvas is the window, and nothing outside it is seen.
    fn new_popup(&mut self, surface: PopupSurface, positioner: PositionerState) {
        let geometry = self.popup_geometry(&surface, &positioner);
        surface.with_pending_state(|state| state.geometry = geometry);
        let _ = self.popups.track_popup(PopupKind::Xdg(surface));
    }

    /// A menu takes the keyboard and the pointer until it is dismissed:
    /// keys go to it, and a click outside closes it and every menu it
    /// opened (`popup_done`). Smithay's anvil does the same.
    fn grab(
        &mut self,
        surface: PopupSurface,
        seat: smithay::reexports::wayland_server::protocol::wl_seat::WlSeat,
        serial: Serial,
    ) {
        let Some(seat) = Seat::<State>::from_resource(&seat) else {
            return;
        };
        let kind = PopupKind::Xdg(surface);
        let Ok(root) = find_popup_root_surface(&kind) else {
            return;
        };
        let Ok(mut grab) = self.popups.grab_popup(root, kind, &seat, serial) else {
            return;
        };
        // A grab another one holds, other than the menu this one opens
        // from, may not be taken over.
        let previous = grab.previous_serial().unwrap_or_else(|| grab.serial());
        if let Some(keyboard) = seat.get_keyboard() {
            if keyboard.is_grabbed() && !(keyboard.has_grab(serial) || keyboard.has_grab(previous))
            {
                grab.ungrab(PopupUngrabStrategy::All);
                return;
            }
            keyboard.set_focus(self, grab.current_grab(), serial);
            keyboard.set_grab(self, PopupKeyboardGrab::new(&grab), serial);
        }
        if let Some(pointer) = seat.get_pointer() {
            if pointer.is_grabbed() && !(pointer.has_grab(serial) || pointer.has_grab(previous)) {
                grab.ungrab(PopupUngrabStrategy::All);
                return;
            }
            pointer.set_grab(self, PopupPointerGrab::new(&grab), serial, Focus::Keep);
        }
    }

    fn reposition_request(
        &mut self,
        surface: PopupSurface,
        positioner: PositionerState,
        token: u32,
    ) {
        let geometry = self.popup_geometry(&surface, &positioner);
        surface.with_pending_state(|state| {
            state.geometry = geometry;
            state.positioner = positioner;
        });
        surface.send_repositioned(token);
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
delegate_primary_selection!(State);
delegate_data_control!(State);
delegate_ext_data_control!(State);
delegate_xdg_decoration!(State);
delegate_viewporter!(State);
delegate_fractional_scale!(State);
delegate_cursor_shape!(State);

/// A Wayland compositor that draws nowhere, and hands every window's
/// pixels to Python.
#[pyclass(unsendable, module = "pysmithay")]
struct Compositor {
    /// The sockets, until `shutdown`.
    wire: Option<Wire>,
    state: State,
    /// The tag the next `connect` gives; 0 is the listening socket's.
    next_tag: u64,
    name: String,
    output: Output,
    seat: Seat<State>,
    keyboard: KeyboardHandle<State>,
    pointer: PointerHandle<State>,
    /// Draws every window into its canvas, in software.
    renderer: PixmanRenderer,
}

/// What a compositor holds open: its clients, and the socket they find.
///
/// `shutdown` drops it on the thread that owns the compositor. PyO3 runs
/// no destructor of an `unsendable` class freed on another thread, and
/// Python's garbage collector may free one on any. Lillecarl/pymux#642.
struct Wire {
    display: Display<State>,
    listener: ListeningSocket,
}

fn closed() -> PyErr {
    PyOSError::new_err("the compositor is closed")
}

/// An awaitable that has its answer already, so that a call answers an
/// awaitable on every path.
fn ready<'py, T>(py: Python<'py>, value: T) -> PyResult<Bound<'py, PyAny>>
where
    T: for<'a> IntoPyObject<'a> + Send + 'static,
{
    pyo3_async_runtimes::tokio::future_into_py(py, async move { Ok(value) })
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

    fn toplevel_mut(&mut self, id: u64) -> PyResult<&mut Toplevel> {
        self.state
            .toplevels
            .iter_mut()
            .find(|toplevel| toplevel.id == id)
            .ok_or_else(|| PyKeyError::new_err(id))
    }

    fn wire(&mut self) -> PyResult<&mut Wire> {
        self.wire.as_mut().ok_or_else(closed)
    }

    fn flush(&mut self) -> PyResult<()> {
        self.wire()?.display.flush_clients().map_err(os_error)
    }
}

#[pymethods]
impl Compositor {
    /// Listen on `$XDG_RUNTIME_DIR/<socket_name>`, on `socket_name`
    /// itself when it is an absolute path, or on the first free
    /// `wayland-N` when no name is given.
    #[new]
    #[pyo3(signature = (socket_name=None, width=800, height=600))]
    fn new(socket_name: Option<&str>, width: i32, height: i32) -> PyResult<Self> {
        let display = Display::<State>::new().map_err(os_error)?;
        let handle = display.handle();
        let listener = match socket_name {
            Some(path) if path.starts_with('/') => {
                ListeningSocket::bind_absolute(PathBuf::from(path))
            }
            Some(name) => ListeningSocket::bind(name),
            None => ListeningSocket::bind_auto("wayland", 1..33),
        }
        .map_err(os_error)?;
        let name = match socket_name {
            Some(name) => name.to_owned(),
            None => listener
                .socket_name()
                .map(|name| name.to_string_lossy().into_owned())
                .unwrap_or_default(),
        };

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

        // wl-copy and wl-paste reach the clipboard through data control
        // when no window of theirs has focus, which here is always.
        let primary_selection_state = PrimarySelectionState::new::<State>(&handle);
        let wlr_data_control_state = wlr_data_control::DataControlState::new::<State, _>(
            &handle,
            Some(&primary_selection_state),
            |_| true,
        );
        let ext_data_control_state = ext_data_control::DataControlState::new::<State, _>(
            &handle,
            Some(&primary_selection_state),
            |_| true,
        );

        let state = State {
            // Version 6 has `preferred_buffer_scale`, which `tell_scale` sends.
            compositor_state: CompositorState::new_v6::<State>(&handle),
            xdg_shell_state: XdgShellState::new::<State>(&handle),
            shm_state: ShmState::new::<State>(&handle, vec![]),
            _output_manager_state: OutputManagerState::new_with_xdg_output::<State>(&handle),
            seat_state,
            data_device_state: DataDeviceState::new::<State>(&handle),
            primary_selection_state,
            wlr_data_control_state,
            ext_data_control_state,
            _xdg_decoration_state: XdgDecorationState::new::<State>(&handle),
            _viewporter_state: ViewporterState::new::<State>(&handle),
            _fractional_scale_state: FractionalScaleManagerState::new::<State>(&handle),
            _cursor_shape_state: CursorShapeManagerState::new::<State>(&handle),
            pointer_over: None,
            output: output.clone(),
            popups: PopupManager::default(),
            toplevels: Vec::new(),
            next_id: 1,
            events: Vec::new(),
        };
        Ok(Self {
            wire: Some(Wire { display, listener }),
            state,
            next_tag: 1,
            name,
            output,
            seat,
            keyboard,
            pointer,
            renderer: PixmanRenderer::new().map_err(os_error)?,
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
        let mime_types: Vec<String> = offers.keys().cloned().collect();
        let handle = self.wire()?.display.handle();
        match target_of(target)? {
            SelectionTarget::Clipboard => {
                set_data_device_selection(&handle, &self.seat, mime_types, Arc::new(offers))
            }
            SelectionTarget::Primary => {
                set_primary_selection(&handle, &self.seat, mime_types, Arc::new(offers))
            }
        }
        self.flush()
    }

    /// Drop the selection, whoever set it.
    fn clear_selection(&mut self, target: &str) -> PyResult<()> {
        let handle = self.wire()?.display.handle();
        match target_of(target)? {
            SelectionTarget::Clipboard => clear_data_device_selection(&handle, &self.seat),
            SelectionTarget::Primary => clear_primary_selection(&handle, &self.seat),
        }
        self.flush()
    }

    /// Ask the client that holds the selection for it in `mime_type`.
    ///
    /// Returns the read end of a pipe, which the caller owns and reads
    /// to the end. The client writes only once `dispatch` has run, so
    /// read it without blocking the loop that calls `dispatch`.
    fn request_selection(&mut self, target: &str, mime_type: String) -> PyResult<i32> {
        let (reader, writer) = std::io::pipe().map_err(os_error)?;
        let writer = OwnedFd::from(writer);
        match target_of(target)? {
            SelectionTarget::Clipboard => {
                request_data_device_client_selection(&self.seat, mime_type, writer)
                    .map_err(|error| PyValueError::new_err(error.to_string()))?
            }
            SelectionTarget::Primary => {
                request_primary_client_selection(&self.seat, mime_type, writer)
                    .map_err(|error| PyValueError::new_err(error.to_string()))?
            }
        }
        self.flush()?;
        Ok(OwnedFd::from(reader).into_raw_fd())
    }

    /// Give the keyboard to this window.
    ///
    /// Not while a menu holds the keyboard: the keys are the menu's
    /// until it is dismissed.
    fn focus(&mut self, id: u64) -> PyResult<()> {
        let surface = self.toplevel(id)?.surface().wl_surface().clone();
        if !self.keyboard.is_grabbed() {
            self.keyboard
                .set_focus(&mut self.state, Some(surface), SERIAL_COUNTER.next_serial());
        }
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

    /// Move the pointer to `(x, y)` in the window's pixels, as the canvas
    /// shows them. It goes to whichever surface is under it there: a
    /// popup, a subsurface, or the window itself.
    fn pointer_motion(&mut self, id: u64, x: f64, y: f64, time: u32) -> PyResult<()> {
        let toplevel = self.toplevel(id)?;
        let window = &toplevel.window;
        // The canvas starts at the window's geometry; its surfaces count
        // from the window's own origin.
        let origin = window.geometry().loc.to_f64();
        let location =
            Point::<f64, Logical>::from((x / toplevel.scale, y / toplevel.scale)) + origin;
        let focus = window
            .surface_under(location, WindowSurfaceType::ALL)
            .map(|(surface, at)| (surface, at.to_f64()));
        self.state.pointer_over = Some(id);
        self.pointer.motion(
            &mut self.state,
            focus,
            &MotionEvent {
                location,
                serial: SERIAL_COUNTER.next_serial(),
                time,
            },
        );
        self.pointer.frame(&mut self.state);
        self.flush()
    }

    /// Scroll the wheel by `steps` notches: positive is down, or right
    /// when `horizontal`. One notch is 15 units of scroll, as libinput
    /// counts a wheel click.
    #[pyo3(signature = (steps, time, horizontal=false))]
    fn pointer_scroll(&mut self, steps: i32, time: u32, horizontal: bool) -> PyResult<()> {
        let axis = if horizontal {
            Axis::Horizontal
        } else {
            Axis::Vertical
        };
        let frame = AxisFrame::new(time)
            .source(AxisSource::Wheel)
            .value(axis, 15.0 * f64::from(steps))
            .v120(axis, 120 * steps);
        self.pointer.axis(&mut self.state, frame);
        self.pointer.frame(&mut self.state);
        self.flush()
    }

    /// Scroll window `id` by `pixels` of its canvas: positive is down,
    /// or right when `horizontal`. A continuous source, so the client
    /// moves by exactly that much and adds no animation or momentum of
    /// its own: the terminal's trackpad already carries both.
    #[pyo3(signature = (id, pixels, time, horizontal=false))]
    fn pointer_scroll_smooth(
        &mut self,
        id: u64,
        pixels: f64,
        time: u32,
        horizontal: bool,
    ) -> PyResult<()> {
        let scale = self.toplevel(id)?.scale;
        let axis = if horizontal {
            Axis::Horizontal
        } else {
            Axis::Vertical
        };
        let frame = AxisFrame::new(time)
            .source(AxisSource::Continuous)
            .value(axis, pixels / scale);
        self.pointer.axis(&mut self.state, frame);
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

    /// What a client puts in `WAYLAND_DISPLAY`: a name in
    /// `$XDG_RUNTIME_DIR`, or an absolute path.
    #[getter]
    fn socket_name(&self) -> &str {
        &self.name
    }

    /// The listening socket and the display: wait on both for reading.
    fn fds(&mut self) -> PyResult<(i32, i32)> {
        let wire = self.wire()?;
        Ok((
            wire.listener.as_raw_fd(),
            wire.display.backend().poll_fd().as_fd().as_raw_fd(),
        ))
    }

    /// Let every client go and stop listening. Nothing works after it.
    fn shutdown(&mut self) {
        self.wire = None;
        self.state.toplevels.clear();
    }

    /// A client connected already, for a program to take as
    /// `WAYLAND_SOCKET`. Answers `(tag, fd)`: the windows of that
    /// connection say `tag` in their "toplevel" event. The caller owns
    /// `fd`, and closes its copy once the program has it. No path is
    /// made, so nothing is left behind.
    fn connect(&mut self) -> PyResult<(u64, i32)> {
        let (ours, theirs) = UnixStream::pair().map_err(os_error)?;
        let tag = self.next_tag;
        self.next_tag += 1;
        let data = ClientState {
            compositor_state: CompositorClientState::default(),
            origin: tag,
        };
        self.wire()?
            .display
            .handle()
            .insert_client(ours, Arc::new(data))
            .map_err(os_error)?;
        Ok((tag, theirs.into_raw_fd()))
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
        let wire = self.wire.as_mut().ok_or_else(closed)?;
        while let Some(stream) = wire.listener.accept().map_err(os_error)? {
            let data = ClientState {
                compositor_state: CompositorClientState::default(),
                origin: 0,
            };
            wire.display
                .handle()
                .insert_client(stream, Arc::new(data))
                .map_err(os_error)?;
        }
        wire.display
            .dispatch_clients(&mut self.state)
            .map_err(os_error)?;
        self.state.popups.cleanup();
        // Every window a surface of which committed is drawn once, after
        // all the requests: a popup and its parent that commit together
        // make one frame and not two.
        for toplevel in &mut self.state.toplevels {
            if let Some(damage) = toplevel.render(&mut self.renderer) {
                self.state.events.push(Event::Commit(toplevel.id, damage));
            }
        }
        self.flush()?;

        std::mem::take(&mut self.state.events)
            .into_iter()
            .map(|event| {
                Ok(match event {
                    Event::Toplevel(id, origin) => {
                        ("toplevel", id, origin).into_pyobject(py)?.into_any()
                    }
                    Event::Title(id, title) => ("title", id, title).into_pyobject(py)?.into_any(),
                    Event::AppId(id, app_id) => {
                        ("app_id", id, app_id).into_pyobject(py)?.into_any()
                    }
                    Event::Commit(id, damage) => {
                        ("commit", id, damage).into_pyobject(py)?.into_any()
                    }
                    Event::Closed(id) => ("closed", id).into_pyobject(py)?.into_any(),
                    Event::Pointer(id, name) => ("pointer", id, name).into_pyobject(py)?.into_any(),
                    Event::Selection(target, mime_types) => {
                        ("selection", name_of(target), mime_types)
                            .into_pyobject(py)?
                            .into_any()
                    }
                    Event::Send(target, mime_type, fd) => {
                        ("send", name_of(target), mime_type, fd.into_raw_fd())
                            .into_pyobject(py)?
                            .into_any()
                    }
                }
                .unbind())
            })
            .collect()
    }

    /// What a kitty graphics terminal needs to show the window's last
    /// buffer as image `image_id`, given the serial of the last buffer it
    /// was sent (`since`, None for never).
    ///
    /// An awaitable of `(serial, commands, whole)`. `commands` is None
    /// before the window has drawn, and empty when the terminal is up to
    /// date. `whole` says the image was sent again, so its placement has
    /// to be put again too. Edits carry only the damage since `since`,
    /// unless a resize or more history than the window keeps lies in
    /// between.
    ///
    /// The pixels are copied at the call, and the encode runs on a
    /// worker thread: at 1600x900 it takes 12 ms, which the event loop
    /// that awaits it does not wait for. Lillecarl/pymux#631.
    #[pyo3(signature = (id, image_id, since=None))]
    fn kitty_update<'py>(
        &self,
        py: Python<'py>,
        id: u64,
        image_id: u32,
        since: Option<u64>,
    ) -> PyResult<Bound<'py, PyAny>> {
        let toplevel = self.toplevel(id)?;
        let serial = toplevel.serial;
        let Some(canvas) = toplevel.canvas.as_ref() else {
            return ready(py, (serial, None::<String>, false));
        };
        if since == Some(serial) {
            return ready(py, (serial, Some(String::new()), false));
        }
        let damage = toplevel.damage_since(since);
        let pixels = canvas.pixels().to_owned();
        pyo3_async_runtimes::tokio::future_into_py(py, async move {
            let whole = damage.is_none();
            let commands = tokio::task::spawn_blocking(move || {
                let pixels = pixels.view();
                match damage {
                    Some(damage) => kitty::edit(&pixels, image_id, &damage),
                    None => kitty::transmit(&pixels, image_id),
                }
            })
            .await
            .map_err(|error| PyRuntimeError::new_err(error.to_string()))?;
            Ok((serial, Some(commands), whole))
        })
    }

    /// The pixels a reader needs to bring the window up to date, given
    /// the serial of the last frame it has (`since`, None for never).
    ///
    /// An awaitable of `(serial, whole, width, height, rects)`, or None
    /// before the window has drawn. `rects` is a list of `(x, y, w, h,
    /// pixels)` with the pixels as RGB rows, kitty's `f=24`: the whole
    /// frame when `whole`, and otherwise the damage since `since`, merged
    /// as `kitty_update` merges it; empty when the reader is up to date.
    /// The reader encodes it for its terminal itself. Lillecarl/pymux#634.
    #[pyo3(signature = (id, since=None))]
    fn frame_rects<'py>(
        &self,
        py: Python<'py>,
        id: u64,
        since: Option<u64>,
    ) -> PyResult<Bound<'py, PyAny>> {
        let toplevel = self.toplevel(id)?;
        let serial = toplevel.serial;
        let Some(canvas) = toplevel.canvas.as_ref() else {
            return ready(py, None::<(u64, bool, i32, i32, Vec<FrameRect>)>);
        };
        let (width, height) = (canvas.width, canvas.height);
        if since == Some(serial) {
            return ready(
                py,
                Some((serial, false, width, height, Vec::<FrameRect>::new())),
            );
        }
        let damage = toplevel.damage_since(since);
        let pixels = canvas.pixels().to_owned();
        pyo3_async_runtimes::tokio::future_into_py(py, async move {
            let whole = damage.is_none();
            let rects = tokio::task::spawn_blocking(move || {
                kitty::rects(&pixels.view(), damage.as_deref())
                    .into_iter()
                    .map(|((x, y, w, h), raw)| (x, y, w, h, FrameBytes(raw)))
                    .collect::<Vec<FrameRect>>()
            })
            .await
            .map_err(|error| PyRuntimeError::new_err(error.to_string()))?;
            Ok(Some((serial, whole, width, height, rects)))
        })
    }

    /// The window's next frame in `encoder`'s VP9 stream: the first, the
    /// first after a resize, and the first after the reader fell behind
    /// the history are keyframes; the others carry only the blocks
    /// under the damage since the frame `encoder` took last.
    ///
    /// An awaitable of `(serial, keyframe, width, height, data, rects)`,
    /// or None before the window has drawn. `rects` are the rectangles
    /// that changed, grown out to the encoder's blocks: what the reader
    /// takes from the decoded frame. `data` is empty when the reader is
    /// up to date. The encode runs on a worker thread.
    /// Lillecarl/pymux#639.
    fn vp9_frame<'py>(
        &self,
        py: Python<'py>,
        id: u64,
        encoder: Py<vp9::Vp9Encoder>,
    ) -> PyResult<Bound<'py, PyAny>> {
        let toplevel = self.toplevel(id)?;
        let serial = toplevel.serial;
        let Some(canvas) = toplevel.canvas.as_ref() else {
            return ready(py, None::<VideoFrame>);
        };
        let (width, height) = (canvas.width, canvas.height);
        let since = encoder
            .get()
            .last()
            .filter(|&(w, h, _)| (w, h) == (width, height))
            .map(|(_, _, serial)| serial);
        if since == Some(serial) {
            let frame: VideoFrame = (
                serial,
                false,
                width,
                height,
                FrameBytes(Vec::new()),
                Vec::new(),
            );
            return ready(py, Some(frame));
        }
        let damage = toplevel.damage_since(since);
        let pixels = canvas.pixels().to_owned();
        pyo3_async_runtimes::tokio::future_into_py(py, async move {
            let (keyframe, data, rects) = tokio::task::spawn_blocking(move || {
                encoder
                    .get()
                    .encode(&pixels.view(), serial, damage.as_deref())
            })
            .await
            .map_err(|error| PyRuntimeError::new_err(error.to_string()))?
            .map_err(PyRuntimeError::new_err)?;
            let frame: VideoFrame = (serial, keyframe, width, height, FrameBytes(data), rects);
            Ok(Some(frame))
        })
    }

    /// The window as last drawn, as `(width, height, rgba)` with no row
    /// padding, or None before it has drawn.
    fn frame<'py>(
        &self,
        py: Python<'py>,
        id: u64,
    ) -> PyResult<Option<(i32, i32, Bound<'py, PyBytes>)>> {
        let Some(canvas) = self.toplevel(id)?.canvas.as_ref() else {
            return Ok(None);
        };
        let pixels = canvas.pixels();
        let row = pixels.width as usize * 4;
        let mut rgba = Vec::with_capacity(row * pixels.height as usize);
        for line in pixels
            .rgba
            .chunks(pixels.stride)
            .take(pixels.height as usize)
        {
            rgba.extend_from_slice(&line[..row]);
        }
        Ok(Some((pixels.width, pixels.height, PyBytes::new(py, &rgba))))
    }

    /// Ask the window to fill a canvas this size, in pixels, at `scale`
    /// canvas pixels to one of its own: at 2 it lays out in half as many
    /// and draws its buffer twice as dense. The canvas takes the size at
    /// once, so a window that keeps a smaller buffer shows the rest as
    /// the clear colour and a larger one is cut off.
    #[pyo3(signature = (id, width, height, scale=1.0))]
    fn configure(&mut self, id: u64, width: i32, height: i32, scale: f64) -> PyResult<()> {
        if !(scale.is_finite() && scale > 0.0) {
            return Err(PyValueError::new_err(format!(
                "a scale is a positive number, not {scale}"
            )));
        }
        let toplevel = self.toplevel_mut(id)?;
        toplevel.wanted = Some((width, height));
        toplevel.dirty = true;
        if toplevel.scale != scale {
            toplevel.scale = scale;
            toplevel.tell_scale();
        }
        let size = logical(width, height, scale);
        let surface = toplevel.surface().clone();
        surface.with_pending_state(|state| {
            state.size = Some(size);
        });
        // Only for a client that reads its scale from the output; the
        // last window configured speaks for all of them.
        if self.output.current_scale().fractional_scale() != scale {
            self.output.change_current_state(
                None,
                None,
                Some(smithay::output::Scale::Fractional(scale)),
                None,
            );
        }
        if surface.is_initial_configure_sent() {
            surface.send_pending_configure();
        }
        self.flush()
    }

    /// Ask the window to close. The client decides.
    fn close(&mut self, id: u64) -> PyResult<()> {
        self.toplevel(id)?.surface().send_close();
        self.flush()
    }

    /// Tell one window, its popups included, that its last frame was
    /// shown, so it may draw the next. `time` is in milliseconds, from
    /// any fixed start. A window nobody shows gets none, and waits.
    fn frame_done(&mut self, id: u64, time: u32) -> PyResult<()> {
        let output = self.output.clone();
        self.toplevel(id)?.window.send_frame(
            &output,
            Duration::from_millis(u64::from(time)),
            None,
            |_, _| Some(output.clone()),
        );
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
    module.add_class::<Compositor>()?;
    module.add_class::<vp9::Vp9Encoder>()
}
