"""
A window of three kinds of surface, each one colour, so a composed frame
says where each landed:

- the toplevel, 64x32, blue;
- a subsurface, 8x8 at (4, 4), green;
- a popup, 10x6, anchored at (20, 10), red;
- a second popup, 10x6, anchored at (60, 28), which would hang over the
  window's corner and asks to be slid back inside it, yellow.

It prints "ready" once all four have drawn, and stays until killed.
"""

from __future__ import annotations

import mmap

from pywayland.client import Display
from pywayland.protocol.wayland import WlCompositor, WlShm, WlSubcompositor
from pywayland.protocol.xdg_shell import XdgPositioner, XdgWmBase
from pywayland.utils import AnonymousFile

BLUE = bytes([0xFF, 0x00, 0x00, 0xFF])
GREEN = bytes([0x00, 0xFF, 0x00, 0xFF])
RED = bytes([0x00, 0x00, 0xFF, 0xFF])
YELLOW = bytes([0x00, 0xFF, 0xFF, 0xFF])


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
    subcompositor = bind(WlSubcompositor)
    shm = bind(WlShm)
    wm_base = bind(XdgWmBase)
    wm_base.dispatcher["ping"] = lambda wm, serial: wm.pong(serial)

    def buffer_of(width, height, colour):
        size = width * height * 4
        with AnonymousFile(size) as fd:
            pool = shm.create_pool(fd, size)
            pixels = mmap.mmap(fd, size)
        pixels[:] = colour * (width * height)
        return pool.create_buffer(0, width, height, width * 4, WlShm.format.argb8888.value), pixels

    def wait_for(configured):
        while not configured:
            display.dispatch(block=True)

    def acked(xdg_surface):
        configured = []

        def on_configure(xdg, serial) -> None:
            xdg.ack_configure(serial)
            configured.append(serial)

        xdg_surface.dispatcher["configure"] = on_configure
        return configured

    surface = compositor.create_surface()
    xdg_surface = wm_base.get_xdg_surface(surface)
    toplevel = xdg_surface.get_toplevel()
    toplevel.set_title("layers")
    configured = acked(xdg_surface)
    surface.commit()
    wait_for(configured)

    keep = []
    blue, pixels = buffer_of(64, 32, BLUE)
    keep.append(pixels)

    child = compositor.create_surface()
    subsurface = subcompositor.get_subsurface(child, surface)
    subsurface.set_position(4, 4)
    subsurface.set_desync()
    green, pixels = buffer_of(8, 8, GREEN)
    keep.append(pixels)
    child.attach(green, 0, 0)
    child.damage_buffer(0, 0, 8, 8)
    child.commit()

    surface.attach(blue, 0, 0)
    surface.damage_buffer(0, 0, 64, 32)
    surface.commit()

    for anchor, colour, slide in (((20, 10), RED, False), ((60, 28), YELLOW, True)):
        positioner = wm_base.create_positioner()
        positioner.set_size(10, 6)
        positioner.set_anchor_rect(anchor[0], anchor[1], 1, 1)
        positioner.set_anchor(XdgPositioner.anchor.top_left.value)
        positioner.set_gravity(XdgPositioner.gravity.bottom_right.value)
        if slide:
            positioner.set_constraint_adjustment(
                XdgPositioner.constraint_adjustment.slide_x.value | XdgPositioner.constraint_adjustment.slide_y.value
            )
        popup_surface = compositor.create_surface()
        popup_xdg = wm_base.get_xdg_surface(popup_surface)
        popup_xdg.get_popup(xdg_surface, positioner)
        configured = acked(popup_xdg)
        popup_surface.commit()
        wait_for(configured)
        buffer, pixels = buffer_of(10, 6, colour)
        keep.append(pixels)
        popup_surface.attach(buffer, 0, 0)
        popup_surface.damage_buffer(0, 0, 10, 6)
        popup_surface.commit()

    display.roundtrip()
    print("ready", flush=True)
    while True:
        display.dispatch(block=True)


if __name__ == "__main__":
    main()
