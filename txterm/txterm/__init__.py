"""
A terminal widget for Textual.

    from textual.app import App, ComposeResult
    from txterm import Terminal

    class Shell(App):
        def compose(self) -> ComposeResult:
            yield Terminal(["bash"])

The parsing is `pyte.screen`, which imports no toolkit, and the pty is
`ptyhost`. What is here is the drawing and the keys: the two things that
belong to Textual and to nothing else. Lillecarl/pymux#82.
"""
from .app import TerminalApp
from .terminal import Terminal

__all__ = ["Terminal", "TerminalApp"]
