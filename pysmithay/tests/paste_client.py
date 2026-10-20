"""
A window that pastes, the way Firefox does: through its `wl_data_device`,
which hears of a selection only while the window has the keyboard.

It opens one window, waits for the clipboard's offer, reads it as text,
and prints it. With no offer by the deadline it prints nothing.
"""

from __future__ import annotations

import os
import sys
import time

from pywayland.client import Display
from pywayland.protocol.wayland import WlCompositor, WlDataDeviceManager, WlSeat
from pywayland.protocol.xdg_shell import XdgWmBase

TEXT = "text/plain;charset=utf-8"
DEADLINE = 8.0


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
    device = bind(WlDataDeviceManager).get_data_device(seat)

    types: dict[object, list[str]] = {}
    selection = []

    def on_offer(_device, offer):
        types[offer] = []
        offer.dispatcher["offer"] = lambda offer, mime_type: types[offer].append(mime_type)

    device.dispatcher["data_offer"] = on_offer
    device.dispatcher["selection"] = lambda _device, offer: selection.append(offer)

    surface = compositor.create_surface()
    xdg_surface = wm_base.get_xdg_surface(surface)
    xdg_surface.get_toplevel().set_title("paste")
    xdg_surface.dispatcher["configure"] = lambda xdg, serial: xdg.ack_configure(serial)
    surface.commit()

    # `roundtrip` and not `dispatch(block=False)`, which only runs what
    # is queued already and never reads the socket.
    deadline = time.monotonic() + DEADLINE
    while not (selection and selection[-1] is not None) and time.monotonic() < deadline:
        display.roundtrip()
        time.sleep(0.02)
    if selection and selection[-1] is not None and TEXT in types.get(selection[-1], []):
        reader, writer = os.pipe()
        selection[-1].receive(TEXT, writer)
        display.flush()
        os.close(writer)
        with os.fdopen(reader, "rb") as pipe:
            sys.stdout.buffer.write(pipe.read())
    # pywayland destroys whatever proxy is left at exit, after the
    # display: that crashes unless the display goes first, by hand.
    display.disconnect()


if __name__ == "__main__":
    main()
