#!/usr/bin/env python
"""
Two shells side by side.

    python examples/two_splits.py

This is the smallest thing that is not one terminal, and it is where the
two questions a multiplexer has to answer first show up:

- **Which pane has the keyboard.** Only the focused one, and only it
  draws a cursor.
- **Which keys the panes do not get.** Every key a terminal gets is a
  key the program in it decides, so a key for the layout has to be
  taken before any pane sees it. Textual calls that a priority binding,
  and tmux calls it a prefix. There are two here: one to move the focus,
  and one to quit.

Lillecarl/pymux#82.
"""

from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal

from txterm import Terminal


class TwoSplits(App):
    "Two terminals, side by side."

    CSS = """
    Terminal {
        border: round $panel;
    }
    Terminal:focus {
        border: round $accent;
    }
    """

    # Priority, so the panes never see these two. Everything else goes
    # to the focused terminal, including "tab" and "ctrl+c".
    BINDINGS = [
        Binding("ctrl+b", "next_pane", "Next pane", priority=True, show=False),
        Binding("ctrl+q", "quit", "Quit", priority=True, show=False),
    ]
    ENABLE_COMMAND_PALETTE = False

    def compose(self) -> ComposeResult:
        with Horizontal():
            yield Terminal(["/bin/bash"])
            yield Terminal(["/bin/bash"])

    def on_mount(self) -> None:
        self.query(Terminal).first().focus()

    def action_next_pane(self) -> None:
        self.screen.focus_next(Terminal)

    def on_terminal_exited(self, event: Terminal.Exited) -> None:
        "A shell that ends takes its pane with it."
        event.terminal.remove()
        if not self.query(Terminal):
            self.exit()


if __name__ == "__main__":
    TwoSplits().run()
