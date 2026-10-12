"""
A window that asks for a pointer shape, the way Firefox does over a
link: `wp_cursor_shape_v1`, with the serial of the pointer's entry. It
prints "ready" once it drew, then asks for "pointer" each time the
pointer enters.
"""

from __future__ import annotations

import mmap

from pywayland.client import Display
from pywayland.protocol.cursor_shape_v1 import WpCursorShapeDeviceV1, WpCursorShapeManagerV1
from pywayland.protocol.wayland import WlCompositor, WlSeat, WlShm
from pywayland.protocol.xdg_shell import XdgWmBase
from pywayland.utils import AnonymousFile


def main() -> None:
    display = Display()
    display.connect()
    registry = display.get_registry()
    offered = {}
    registry.dispatcher["global"] = lambda _r, name, interface, version: offered.update({interface: (name, version)})
    display.roundtrip()

    def bind(interface):
        name, version = offered[interface.name]
        return registry.bind(name, interface, min(version, interface.version))

    compositor = bind(WlCompositor)
    shm = bind(WlShm)
    wm_base = bind(XdgWmBase)
    wm_base.dispatcher["ping"] = lambda wm, serial: wm.pong(serial)
    seat = bind(WlSeat)
    pointer = seat.get_pointer()
    device = bind(WpCursorShapeManagerV1).get_pointer(pointer)
    pointer.dispatcher["enter"] = lambda _p, serial, *_rest: device.set_shape(
        serial, WpCursorShapeDeviceV1.shape.pointer.value
    )

    surface = compositor.create_surface()
    xdg_surface = wm_base.get_xdg_surface(surface)
    xdg_surface.get_toplevel()
    configured = []

    def on_configure(xdg, serial):
        xdg.ack_configure(serial)
        configured.append(serial)

    xdg_surface.dispatcher["configure"] = on_configure
    surface.commit()
    while not configured:
        display.dispatch(block=True)

    width, height = 64, 32
    size = width * height * 4
    with AnonymousFile(size) as fd:
        pool = shm.create_pool(fd, size)
        pixels = mmap.mmap(fd, size)
    pixels[:] = bytes([0x80, 0x80, 0x80, 0xFF]) * (width * height)
    surface.attach(pool.create_buffer(0, width, height, width * 4, WlShm.format.argb8888.value), 0, 0)
    surface.damage_buffer(0, 0, width, height)
    surface.commit()
    display.roundtrip()
    print("ready", flush=True)
    while display.dispatch(block=True) != -1:
        pass


if __name__ == "__main__":
    main()
