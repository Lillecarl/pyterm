//! `zwp_text_input_v3`, served by the compositor itself.
//!
//! A character the keymap has no key for -- é on xkb's default US
//! keymap, every emoji -- cannot be pressed, so it goes to the window as
//! text, the way an input method commits it. smithay's own text input
//! drops every request while no input method client is connected, and
//! here the compositor is the one with the text. Lillecarl/pymux#624.
//!
//! The protocol, in short: the compositor says `enter` and `leave` as
//! the keyboard moves; a window that has a text field under its focus
//! enables text input and commits; the compositor sends
//! `commit_string` and then `done`, whose serial is how many times the
//! window committed.

use smithay::reexports::wayland_protocols::wp::text_input::zv3::server::{
    zwp_text_input_manager_v3::{self, ZwpTextInputManagerV3},
    zwp_text_input_v3::{self, ZwpTextInputV3},
};
use smithay::reexports::wayland_server::backend::ClientId;
use smithay::reexports::wayland_server::protocol::wl_surface::WlSurface;
use smithay::reexports::wayland_server::{
    Client, DataInit, Dispatch, DisplayHandle, GlobalDispatch, New, Resource,
};

use crate::State;

/// The text inputs of every client, and the surface with the keyboard.
#[derive(Default)]
pub struct TextInputs {
    instances: Vec<Instance>,
    focus: Option<WlSurface>,
    /// Text for the surface with the keyboard, held until its window
    /// enables text input: the keyboard moves with the key that brings
    /// the text, and the window answers `enter` a dispatch later.
    held: Vec<String>,
}

struct Instance {
    object: ZwpTextInputV3,
    /// How many times the window committed: the serial `done` names.
    commits: u32,
    /// What the next commit makes of `enabled`.
    pending: Option<bool>,
    enabled: bool,
}

impl TextInputs {
    pub fn new(display: &DisplayHandle) -> Self {
        display.create_global::<State, ZwpTextInputManagerV3, ()>(1, ());
        Self::default()
    }

    /// The keyboard moved: `leave` for the old surface's text inputs,
    /// which disables them, and `enter` for the new one's.
    pub fn set_focus(&mut self, surface: Option<&WlSurface>) {
        if self.focus.as_ref() == surface {
            return;
        }
        self.held.clear();
        if let Some(old) = self.focus.take() {
            for instance in self.instances.iter_mut() {
                if instance.object.id().same_client_as(&old.id()) {
                    instance.object.leave(&old);
                    instance.enabled = false;
                    instance.pending = None;
                }
            }
        }
        if let Some(new) = surface {
            for instance in &self.instances {
                if instance.object.id().same_client_as(&new.id()) {
                    instance.object.enter(new);
                }
            }
            self.focus = Some(new.clone());
        }
    }

    /// Give `text` to the enabled text inputs of the surface with the
    /// keyboard, or hold it for one that is not enabled yet. False when
    /// that window has no text input at all.
    pub fn commit_text(&mut self, text: &str) -> bool {
        let Some(focus) = &self.focus else {
            return false;
        };
        let mut sent = false;
        let mut waiting = false;
        for instance in &self.instances {
            if !instance.object.id().same_client_as(&focus.id()) {
                continue;
            }
            if instance.enabled {
                instance.object.commit_string(Some(text.to_owned()));
                instance.object.done(instance.commits);
                sent = true;
            } else {
                waiting = true;
            }
        }
        if !sent && waiting {
            self.held.push(text.to_owned());
            return true;
        }
        sent
    }

    fn add(&mut self, object: ZwpTextInputV3) {
        // A text input made while its window has the keyboard is entered
        // at once: no focus change would tell it otherwise.
        if let Some(focus) = &self.focus {
            if object.id().same_client_as(&focus.id()) {
                object.enter(focus);
            }
        }
        self.instances.push(Instance {
            object,
            commits: 0,
            pending: None,
            enabled: false,
        });
    }

    fn request(&mut self, object: &ZwpTextInputV3, request: zwp_text_input_v3::Request) {
        let Some(instance) = self
            .instances
            .iter_mut()
            .find(|instance| instance.object == *object)
        else {
            return;
        };
        match request {
            zwp_text_input_v3::Request::Enable => instance.pending = Some(true),
            zwp_text_input_v3::Request::Disable => instance.pending = Some(false),
            zwp_text_input_v3::Request::Commit => {
                instance.commits = instance.commits.wrapping_add(1);
                if let Some(enabled) = instance.pending.take() {
                    instance.enabled = enabled;
                }
                if instance.enabled && !self.held.is_empty() {
                    for text in self.held.drain(..) {
                        instance.object.commit_string(Some(text));
                        instance.object.done(instance.commits);
                    }
                }
            }
            // Surrounding text, content type, cursor rectangle: what an
            // input method composes with, and this one composes nothing.
            _ => {}
        }
    }

    fn remove(&mut self, object: &ZwpTextInputV3) {
        self.instances.retain(|instance| instance.object != *object);
    }
}

impl GlobalDispatch<ZwpTextInputManagerV3, ()> for State {
    fn bind(
        _state: &mut Self,
        _handle: &DisplayHandle,
        _client: &Client,
        resource: New<ZwpTextInputManagerV3>,
        _global_data: &(),
        data_init: &mut DataInit<'_, Self>,
    ) {
        data_init.init(resource, ());
    }
}

impl Dispatch<ZwpTextInputManagerV3, ()> for State {
    fn request(
        state: &mut Self,
        _client: &Client,
        _resource: &ZwpTextInputManagerV3,
        request: zwp_text_input_manager_v3::Request,
        _data: &(),
        _handle: &DisplayHandle,
        data_init: &mut DataInit<'_, Self>,
    ) {
        if let zwp_text_input_manager_v3::Request::GetTextInput { id, .. } = request {
            let object = data_init.init(id, ());
            state.text_inputs.add(object);
        }
    }
}

impl Dispatch<ZwpTextInputV3, ()> for State {
    fn request(
        state: &mut Self,
        _client: &Client,
        resource: &ZwpTextInputV3,
        request: zwp_text_input_v3::Request,
        _data: &(),
        _handle: &DisplayHandle,
        _data_init: &mut DataInit<'_, Self>,
    ) {
        state.text_inputs.request(resource, request);
    }

    fn destroyed(state: &mut Self, _client: ClientId, resource: &ZwpTextInputV3, _data: &()) {
        state.text_inputs.remove(resource);
    }
}
