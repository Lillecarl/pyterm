"""
A Wayland client that draws at the scale it is told.

It waits for a configure with a size and for a preferred scale, then
fills a buffer of the size times the scale, with one red pixel in the
last corner, and prints `<width> <height> <scale>` as it was told them.

With `--integer` it takes the scale from `wl_surface.preferred_buffer_scale`
and shows the buffer with `set_buffer_scale`; otherwise from
`wp_fractional_scale_v1`, shown through a viewport.
"""

from __future__ import annotations

import mmap
import sys

from pywayland.client import Display
from pywayland.protocol.fractional_scale_v1 import WpFractionalScaleManagerV1
from pywayland.protocol.viewporter import WpViewporter
from pywayland.protocol.wayland import WlCompositor, WlShm
from pywayland.protocol.xdg_shell import XdgWmBase
from pywayland.utils import AnonymousFile

FILL = bytes([0x99, 0x66, 0x33, 0xFF])
RED = bytes([0x00, 0x00, 0xFF, 0xFF])


def main() -> None:
    integer = "--integer" in sys.argv
    display = Display()
    display.connect()
    registry = display.get_registry()
    offered = {}
    registry.dispatcher["global"] = lambda _registry, name, interface, version: offered.update(
        {interface: (name, version)}
    )
    display.roundtrip()

    def bind(interface, version=None):
        name, offered_version = offered[interface.name]
        return registry.bind(name, interface, version or min(offered_version, interface.version))

    compositor = bind(WlCompositor, 6)
    shm = bind(WlShm)
    wm_base = bind(XdgWmBase)
    wm_base.dispatcher["ping"] = lambda wm, serial: wm.pong(serial)

    surface = compositor.create_surface()
    told = {}
    if integer:
        surface.dispatcher["preferred_buffer_scale"] = lambda _surface, factor: told.update(scale=factor * 120)
    else:
        fractional = bind(WpFractionalScaleManagerV1).get_fractional_scale(surface)
        fractional.dispatcher["preferred_scale"] = lambda _fractional, scale: told.update(scale=scale)
        viewport = bind(WpViewporter).get_viewport(surface)
    xdg_surface = wm_base.get_xdg_surface(surface)
    toplevel = xdg_surface.get_toplevel()
    toplevel.set_title("scaled")
    toplevel.dispatcher["configure"] = lambda _toplevel, width, height, _states: told.update(size=(width, height))
    xdg_surface.dispatcher["configure"] = lambda xdg, serial: xdg.ack_configure(serial)
    surface.commit()
    while not (told.get("size", (0, 0))[0] and told.get("scale", 120) != 120):
        display.dispatch(block=True)

    logical_width, logical_height = told["size"]
    scale = told["scale"]
    width, height = logical_width * scale // 120, logical_height * scale // 120
    stride = width * 4
    size = stride * height
    with AnonymousFile(size) as fd:
        pool = shm.create_pool(fd, size)
        pixels = mmap.mmap(fd, size)
    buffer = pool.create_buffer(0, width, height, stride, WlShm.format.argb8888.value)
    pixels[:] = FILL * (width * height)
    pixels[size - 4 :] = RED
    if integer:
        surface.set_buffer_scale(scale // 120)
    else:
        viewport.set_destination(logical_width, logical_height)
    surface.attach(buffer, 0, 0)
    surface.damage_buffer(0, 0, width, height)
    surface.commit()
    print(logical_width, logical_height, scale, flush=True)
    while True:
        display.dispatch(block=True)


if __name__ == "__main__":
    main()
