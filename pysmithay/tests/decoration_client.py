"""
A window that asks who draws its title bar, and prints the answer: the
mode of the first decoration configure, 1 for client side, 2 for server
side.
"""

from __future__ import annotations

from pywayland.client import Display
from pywayland.protocol.wayland import WlCompositor
from pywayland.protocol.xdg_decoration_unstable_v1 import ZxdgDecorationManagerV1, ZxdgToplevelDecorationV1
from pywayland.protocol.xdg_shell import XdgWmBase


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
    wm_base = bind(XdgWmBase)
    decorations = bind(ZxdgDecorationManagerV1)

    surface = compositor.create_surface()
    xdg_surface = wm_base.get_xdg_surface(surface)
    toplevel = xdg_surface.get_toplevel()
    decoration = decorations.get_toplevel_decoration(toplevel)
    modes = []
    decoration.dispatcher["configure"] = lambda _decoration, mode: modes.append(mode)
    # Ask to draw its own; the compositor answers what it will have.
    decoration.set_mode(ZxdgToplevelDecorationV1.mode.client_side.value)
    configured = []

    def on_configure(xdg, serial) -> None:
        xdg.ack_configure(serial)
        configured.append(serial)

    xdg_surface.dispatcher["configure"] = on_configure
    surface.commit()
    while not (configured and modes):
        display.dispatch(block=True)
    print(modes[0], flush=True)
    display.disconnect()


if __name__ == "__main__":
    main()
