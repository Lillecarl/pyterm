"""
A window that takes text the way a text field does: through
`zwp_text_input_v3`, enabled while it has the keyboard.

It prints "enabled" once it enabled text input on focus, then
"text <string>" for each string the compositor commits.
"""

from __future__ import annotations

from pywayland.client import Display
from pywayland.protocol.text_input_unstable_v3 import ZwpTextInputManagerV3
from pywayland.protocol.wayland import WlCompositor, WlSeat
from pywayland.protocol.xdg_shell import XdgWmBase


def main() -> None:
    display = Display()
    display.connect()
    registry = display.get_registry()
    offered = {}
    registry.dispatcher["global"] = lambda _registry, name, interface, version: offered.update(
        {interface: (name, version)}
    )
    display.roundtrip()

    def bind(interface):
        name, version = offered[interface.name]
        return registry.bind(name, interface, min(version, interface.version))

    compositor = bind(WlCompositor)
    wm_base = bind(XdgWmBase)
    wm_base.dispatcher["ping"] = lambda wm, serial: wm.pong(serial)
    seat = bind(WlSeat)
    text_input = bind(ZwpTextInputManagerV3).get_text_input(seat)

    pending = []

    def on_enter(text_input, _surface):
        text_input.enable()
        text_input.commit()
        print("enabled", flush=True)

    def on_done(_text_input, _serial):
        if pending:
            print("text %s" % pending.pop(), flush=True)

    text_input.dispatcher["enter"] = on_enter
    text_input.dispatcher["commit_string"] = lambda _ti, text: pending.append(text or "")
    text_input.dispatcher["done"] = on_done

    surface = compositor.create_surface()
    xdg_surface = wm_base.get_xdg_surface(surface)
    xdg_surface.get_toplevel().set_title("text")
    xdg_surface.dispatcher["configure"] = lambda xdg, serial: xdg.ack_configure(serial)
    surface.commit()
    while display.dispatch(block=True) != -1:
        pass


if __name__ == "__main__":
    main()
