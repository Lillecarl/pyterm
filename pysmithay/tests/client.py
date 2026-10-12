"""
A Wayland client whose every pixel and every damage rectangle is known.

It opens one 64x32 window titled "probe", fills it with one colour, then
paints a 4x4 red square at (10, 5) and damages only that. Then it exits.
"""

from __future__ import annotations

import mmap

from pywayland.client import Display
from pywayland.protocol.wayland import WlCompositor, WlShm
from pywayland.protocol.xdg_shell import XdgWmBase
from pywayland.utils import AnonymousFile

WIDTH, HEIGHT = 64, 32
STRIDE = WIDTH * 4
#: B, G, R, A: what an ARGB8888 word is in memory on a little-endian machine.
FILL = bytes([0x99, 0x66, 0x33, 0xFF])
RED = bytes([0x00, 0x00, 0xFF, 0xFF])
SQUARE = (10, 5, 4, 4)


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
    shm = bind(WlShm)
    wm_base = bind(XdgWmBase)
    wm_base.dispatcher["ping"] = lambda wm, serial: wm.pong(serial)

    surface = compositor.create_surface()
    xdg_surface = wm_base.get_xdg_surface(surface)
    toplevel = xdg_surface.get_toplevel()
    toplevel.set_title("probe")
    toplevel.set_app_id("pysmithay.probe")

    configured = []

    def on_configure(xdg, serial):
        xdg.ack_configure(serial)
        configured.append(serial)

    xdg_surface.dispatcher["configure"] = on_configure
    surface.commit()
    while not configured:
        display.dispatch(block=True)

    size = STRIDE * HEIGHT
    with AnonymousFile(size) as fd:
        pool = shm.create_pool(fd, size)
        pixels = mmap.mmap(fd, size)
    buffer = pool.create_buffer(0, WIDTH, HEIGHT, STRIDE, WlShm.format.argb8888.value)

    pixels[:] = FILL * (WIDTH * HEIGHT)
    surface.attach(buffer, 0, 0)
    surface.damage_buffer(0, 0, WIDTH, HEIGHT)
    shown = []
    surface.frame().dispatcher["done"] = lambda _callback, _time: shown.append(True)
    surface.commit()
    while not shown:
        display.dispatch(block=True)

    x, y, w, h = SQUARE
    for row in range(y, y + h):
        start = row * STRIDE + x * 4
        pixels[start : start + w * 4] = RED * w
    surface.attach(buffer, 0, 0)
    surface.damage_buffer(x, y, w, h)
    surface.commit()
    display.roundtrip()

    toplevel.destroy()
    xdg_surface.destroy()
    surface.destroy()
    display.roundtrip()
    display.disconnect()


if __name__ == "__main__":
    main()
