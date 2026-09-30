"""
A sequence that never finishes must not wedge a widget.

A program can write a partial escape and then stop. The parser then
reads every later byte as part of that sequence, and the widget shows
the wrong screen for ever. `GroundTimer` bounds that. The rule is
pyte's; this checks the widget gives itself one. Lillecarl/pymux#484.
"""

from textual.app import App, ComposeResult

from no_backend import NoBackend
from txterm import Terminal

COLUMNS = 20
LINES = 4
SIZE = (COLUMNS, LINES)


class OneTerminal(App):
    "One terminal, with no program under it."

    BINDINGS: list = []
    ENABLE_COMMAND_PALETTE = False

    def compose(self) -> ComposeResult:
        yield Terminal(backend=NoBackend())


async def test_a_widget_gives_its_parser_a_ground_timer():
    app = OneTerminal()
    async with app.run_test(size=SIZE):
        made = app.query_one(Terminal)
        assert made._ground_timer.timeout == 5
        assert made.process.receive == made._ground_timer.feed
