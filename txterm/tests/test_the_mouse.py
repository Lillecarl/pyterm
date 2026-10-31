"""
A program in the widget hears the mouse it asked for: a click and the
wheel, in the mode it turned on, at the cell under the pointer. The
reports are `pyte.mouse`'s, so these tests read what reaches the
backend, not how a report is spelled. Lillecarl/pymux#842.
"""

from __future__ import annotations

from no_backend import NoBackend
from pyte.modes import PrivateMode
from pyte.mouse import ARROWS_PER_WHEEL_STEP
from pyte.sequences import set_mode
from textual import events

from txterm import Terminal, TerminalApp

#: The size of the pane in every test here.
SIZE = (20, 5)


def wheel(terminal: Terminal, kind: type[events.MouseEvent], column: int, row: int) -> events.MouseEvent:
    "A wheel step over a cell of the terminal, as Textual sends one."
    region = terminal.content_region
    return kind(
        terminal, column, row, 0, 0, 0, False, False, False, screen_x=region.x + column, screen_y=region.y + row
    )


async def test_a_click_reaches_a_program_that_asked_for_sgr_reports():
    backend = NoBackend()
    app = TerminalApp(backend=backend)
    async with app.run_test(size=SIZE) as pilot:
        terminal = app.query_one(Terminal)
        terminal.stream.feed(set_mode(PrivateMode.MOUSE_REPORTING) + set_mode(PrivateMode.SGR_MOUSE))
        await pilot.click(Terminal, offset=(3, 2))
        await pilot.pause()
        # One based, column first; "M" presses and "m" lets go.
        assert backend.written == ["\x1b[<0;4;3M", "\x1b[<0;4;3m"]


async def test_the_wheel_reaches_it_too():
    backend = NoBackend()
    app = TerminalApp(backend=backend)
    async with app.run_test(size=SIZE) as pilot:
        terminal = app.query_one(Terminal)
        terminal.stream.feed(set_mode(PrivateMode.MOUSE_REPORTING) + set_mode(PrivateMode.SGR_MOUSE))
        terminal.post_message(wheel(terminal, events.MouseScrollUp, 1, 0))
        terminal.post_message(wheel(terminal, events.MouseScrollDown, 1, 0))
        await pilot.pause()
        assert backend.written == ["\x1b[<64;2;1M", "\x1b[<65;2;1M"]


async def test_a_program_that_asked_for_no_mouse_hears_nothing():
    backend = NoBackend()
    app = TerminalApp(backend=backend)
    async with app.run_test(size=SIZE) as pilot:
        await pilot.click(Terminal, offset=(3, 2))
        await pilot.pause()
        assert backend.written == []


async def test_the_wheel_on_the_alternate_screen_sends_arrows():
    "A program that wants no mouse there reads the wheel as the arrow keys, as in ptterm."
    backend = NoBackend()
    app = TerminalApp(backend=backend)
    async with app.run_test(size=SIZE) as pilot:
        terminal = app.query_one(Terminal)
        terminal.stream.feed(set_mode(PrivateMode.ALTERNATE_SCREEN_WITH_CURSOR))
        terminal.post_message(wheel(terminal, events.MouseScrollDown, 1, 0))
        await pilot.pause()
        assert "".join(backend.written) == "\x1b[B" * ARROWS_PER_WHEEL_STEP
