"""
A window that opens a menu when it is clicked, the way a GTK menu bar
does: a popup with a grab, made from the click's serial. It prints what
happens, one word a line:

- "ready" once the window drew;
- "menu" once the menu drew;
- "focus window" or "focus menu" when the keyboard enters either;
- "key <code>" with the surface the keyboard is on;
- "done" when the menu is dismissed.
"""

from __future__ import annotations

import mmap

from pywayland.client import Display
from pywayland.protocol.wayland import WlCompositor, WlSeat, WlShm
from pywayland.protocol.xdg_shell import XdgPositioner, XdgWmBase
from pywayland.utils import AnonymousFile


def say(word: str) -> None:
    print(word, flush=True)


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
    keep = []

    def draw(surface, width, height):
        size = width * height * 4
        with AnonymousFile(size) as fd:
            pool = shm.create_pool(fd, size)
            pixels = mmap.mmap(fd, size)
        pixels[:] = bytes([0x80, 0x80, 0x80, 0xFF]) * (width * height)
        keep.append(pixels)
        surface.attach(pool.create_buffer(0, width, height, width * 4, WlShm.format.argb8888.value), 0, 0)
        surface.damage_buffer(0, 0, width, height)
        surface.commit()

    def acked(xdg_surface, then):
        def on_configure(xdg, serial) -> None:
            xdg.ack_configure(serial)
            then()

        xdg_surface.dispatcher["configure"] = on_configure

    surface = compositor.create_surface()
    xdg_surface = wm_base.get_xdg_surface(surface)
    xdg_surface.get_toplevel()
    drawn = []

    def first_draw() -> None:
        if not drawn:
            drawn.append(True)
            draw(surface, 64, 32)
            say("ready")

    acked(xdg_surface, first_draw)
    surface.commit()

    menu_surfaces = []

    def open_menu(serial: int) -> None:
        positioner = wm_base.create_positioner()
        positioner.set_size(20, 10)
        positioner.set_anchor_rect(10, 10, 1, 1)
        positioner.set_anchor(XdgPositioner.anchor.top_left.value)
        positioner.set_gravity(XdgPositioner.gravity.bottom_right.value)
        menu = compositor.create_surface()
        menu_xdg = wm_base.get_xdg_surface(menu)
        popup = menu_xdg.get_popup(xdg_surface, positioner)
        popup.dispatcher["popup_done"] = lambda _popup: say("done")
        popup.grab(seat, serial)
        menu_surfaces.append(menu)

        def menu_draw() -> None:
            draw(menu, 20, 10)
            say("menu")

        acked(menu_xdg, menu_draw)
        menu.commit()

    def name_of(target) -> str:
        return "menu" if target in menu_surfaces else "window"

    pointer = seat.get_pointer()

    def on_button(_pointer, serial, _time, _button, state) -> None:
        if state == 1 and not menu_surfaces:
            open_menu(serial)

    pointer.dispatcher["button"] = on_button
    keyboard = seat.get_keyboard()
    focused = ["none"]

    def on_enter(_keyboard, _serial, target, _keys) -> None:
        focused[0] = name_of(target)
        say("focus " + focused[0])

    keyboard.dispatcher["enter"] = on_enter
    keyboard.dispatcher["key"] = lambda _k, _serial, _time, key, state: (
        say("key %d %s" % (key, focused[0])) if state == 1 else None
    )

    while True:
        display.dispatch(block=True)


if __name__ == "__main__":
    main()
