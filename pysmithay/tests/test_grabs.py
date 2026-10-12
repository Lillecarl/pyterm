"""
A menu opened with a grab takes the keyboard, and a click outside it
dismisses it, as on a desktop.
"""

from __future__ import annotations

import os
import select
import sys
import time
from pathlib import Path

from test_compositor import launch, pump

CLIENT = Path(__file__).with_name("grab_client.py")
BTN_LEFT = 0x110
KEY_A = 30


class Said:
    """
    What the grab client printed, read as it comes.

    Off the descriptor, not the buffered pipe: `readline` takes a whole
    chunk into its buffer and returns one line of it, and `select` then
    says nothing is left for the lines still in there.
    """

    def __init__(self, client) -> None:
        self.client = client
        self.fd = client.stdout.fileno()
        self.text = ""

    @property
    def lines(self) -> list[str]:
        return self.text.splitlines()

    def heard(self, word: str):
        def until(_seen) -> bool:
            while select.select([self.fd], [], [], 0)[0]:
                chunk = os.read(self.fd, 4096)
                if not chunk:
                    break
                self.text += chunk.decode()
            return word in self.lines

        return until


def click(compositor, x, y):
    now = int(time.monotonic() * 1000)
    compositor.pointer_motion(1, x, y, now)
    compositor.pointer_button(BTN_LEFT, True, now)
    compositor.pointer_button(BTN_LEFT, False, now + 1)


def with_a_menu(compositor) -> Said:
    client = launch(compositor, sys.executable, str(CLIENT))
    said = Said(client)
    pump(compositor, said.heard("ready"))
    click(compositor, 5, 5)
    pump(compositor, said.heard("menu"))
    return said


def test_a_menu_takes_the_keyboard(compositor):
    said = with_a_menu(compositor)
    try:
        pump(compositor, said.heard("focus menu"))
        # pymux asks for the window on every key; the menu keeps it.
        compositor.focus(1)
        compositor.key(KEY_A, True, 0)
        compositor.key(KEY_A, False, 1)
        pump(compositor, said.heard("key %d menu" % (KEY_A,)))
    finally:
        said.client.kill()


def test_a_click_on_no_surface_dismisses_the_menu(compositor):
    """
    Past the window's edge, where a pane bigger than the window shows
    nothing. A click on the window itself goes to the window, which
    closes its own menu: Smithay's grab leaves a click on the same
    client to that client, as GTK expects.
    """
    said = with_a_menu(compositor)
    try:
        click(compositor, 100, 100)
        pump(compositor, said.heard("done"))
    finally:
        said.client.kill()
