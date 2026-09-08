"""
How deep the scrollback of a widget goes, and who decides it.

`Screen` drops the rows above its history limit, and the limit reaches
it as a function. Nothing gave `Terminal` a way to pass one, so every
widget kept two thousand rows whatever option the application offered.

The limit is a function and not a number so that a change reaches a
widget that is already running: `Screen` calls it on every prune.

The widget runs in an application of its own, because `TerminalApp`
passes no limit and this is the argument under test.
"""

from textual.app import App, ComposeResult

from no_backend import NoBackend
from txterm import Terminal

COLUMNS = 80
LINES = 24
SIZE = (COLUMNS, LINES)

#: How often `Screen` prunes: one cleanup per hundred linefeeds. So a
#: buffer holds up to a hundred rows more than the limit.
BETWEEN_CLEANUPS = 100


class OneTerminal(App):
    "One terminal, with a scrollback depth of its own."

    BINDINGS: list = []
    ENABLE_COMMAND_PALETTE = False

    def __init__(self, get_history_limit=None) -> None:
        super().__init__()
        self._get_history_limit = get_history_limit

    def compose(self) -> ComposeResult:
        yield Terminal(backend=NoBackend(), get_history_limit=self._get_history_limit)


def scroll(made, rows: int) -> None:
    "Write that many lines, so that the screen scrolls that far."
    made.stream.feed("".join("line %d\r\n" % number for number in range(rows)))


async def test_a_widget_keeps_two_thousand_rows_by_default():
    app = OneTerminal()
    async with app.run_test(size=SIZE):
        made = app.query_one(Terminal)
        scroll(made, 4000)
        kept = len(made.emulator.page.data_buffer)
        assert 2000 <= kept <= 2000 + BETWEEN_CLEANUPS + LINES


async def test_the_application_says_how_deep_the_history_goes():
    app = OneTerminal(lambda: 500)
    async with app.run_test(size=SIZE):
        made = app.query_one(Terminal)
        scroll(made, 4000)
        kept = len(made.emulator.page.data_buffer)
        assert 500 <= kept <= 500 + BETWEEN_CLEANUPS + LINES


async def test_the_limit_is_read_again_while_the_program_runs():
    limit = 2000
    app = OneTerminal(lambda: limit)
    async with app.run_test(size=SIZE):
        made = app.query_one(Terminal)
        scroll(made, 4000)
        assert len(made.emulator.page.data_buffer) > 1000

        limit = 200
        scroll(made, BETWEEN_CLEANUPS)
        kept = len(made.emulator.page.data_buffer)
        assert 200 <= kept <= 200 + BETWEEN_CLEANUPS + LINES
