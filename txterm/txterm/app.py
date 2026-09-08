"""
A whole application that is one terminal.

`Terminal` is a widget, so it lives in a layout that somebody else owns.
This is the smallest owner there is: a screen with one terminal on it,
filling the window.

It exists to be driven. A suite that puts a real terminal in front of
txterm needs a program to run, and "a widget" is not one.
Lillecarl/pymux#82.
"""

from typing import List, Optional

from ptyhost.backends import Backend
from textual.app import App, ComposeResult

from .terminal import Terminal

__all__ = ["TerminalApp"]


class TerminalApp(App):
    """
    One terminal, filling the window.

    **It has no key bindings of its own.** Textual checks two of them
    before the focused widget sees a key at all: "ctrl+q" quits, and
    "ctrl+p" opens the command palette. A terminal that ate two keys
    would be a terminal that cannot run an editor, so both go: the
    empty `BINDINGS` takes the first, and `ENABLE_COMMAND_PALETTE` the
    second. Every other binding of Textual is checked after the widget,
    and `Terminal.on_key` stops the key before it gets there.
    """

    BINDINGS: list = []
    ENABLE_COMMAND_PALETTE = False

    CSS = """
    Screen {
        layout: vertical;
    }
    """

    def __init__(
        self,
        command: Optional[List[str]] = None,
        *,
        backend: Optional[Backend] = None,
    ) -> None:
        super().__init__()
        self._command = command
        self._backend = backend

    def compose(self) -> ComposeResult:
        yield Terminal(self._command, backend=self._backend)

    def on_mount(self) -> None:
        self.query_one(Terminal).focus()

    def on_terminal_exited(self, event: Terminal.Exited) -> None:
        "The program has ended, so the application has nothing left to do."
        self.exit()


def main() -> None:
    "Run one program in one terminal. `txterm <command>`."
    import sys

    TerminalApp(sys.argv[1:] or None).run()
