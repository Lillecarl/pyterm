"""
The widget builds a row again only when the screen wrote it.

`Terminal` keeps the `Strip` it drew for each row of the page and the
write count of the screen that it drew it at. A row whose count has not
moved is a row it hands back as it stands, so a frame after a program
wrote one line builds one line. `ptterm` does the same for
prompt_toolkit, and for the same reason: the state belongs to the
reader, because a screen has more than one and no way to know how many.
Lillecarl/pymux#126.

**A row that is kept and should not have been is a wrong screen, not a
slow one.** So this file does not check the rule. It runs two widgets
side by side over the same bytes: one keeps what it drew, and one is
emptied before every frame so that it builds everything. Every row of
every frame has to match.
"""

from __future__ import annotations

from no_backend import NoBackend
from pyte import escape
from pyte.modes import PrivateMode
from pyte.sequences.csi import csi, reset_mode, set_mode
from pyte.sequences.escapes import Sharp, sharp
from pyterm_pytest.instructions import count_instructions
from rich.style import Style
from textual.geometry import Region
from textual.strip import Strip

from txterm import Terminal, TerminalApp

#: The size of the pane in every test here.
SIZE = (40, 10)
COLUMNS, LINES = SIZE


def frame(terminal: Terminal, forget: bool):
    """
    Every visible row of a widget, as the text and styles a person
    would see.

    `forget` empties what the widget remembers first, which makes it
    build every row.
    """
    if forget:
        terminal._drawn.clear()
        terminal._drawn_at.clear()
    return [[(segment.text, segment.style) for segment in terminal.render_line(y)] for y in range(LINES)]


#: What a real program does, in the shapes that move rows about. Each
#: one is fed to both widgets, and a frame is taken after each.
CHUNKS = [
    "the first line\r\nthe second\r\nthe third",
    csi(escape.CUP, 1, 1) + "over the first",
    csi(escape.SGR, 7) + "reversed" + csi(escape.SGR, 0) + " and not",
    "\r\n" * 12,  # Scroll a long way.
    csi(escape.DECSTBM, 2, 4) + csi(escape.CUP, 3, 1) + "inside a region\r\n\r\n\r\n",
    csi(escape.DECSTBM),  # And the region away again.
    csi(escape.CUP) + csi(escape.ED, 2),  # Clear the screen.
    sharp(Sharp.DECALN),  # DECALN: fill it with E.
    set_mode(PrivateMode.REVERSE_VIDEO),  # DECSCNM: reverse the whole screen.
    "more text after the reverse",
    reset_mode(PrivateMode.REVERSE_VIDEO),
    (
        set_mode(PrivateMode.ALTERNATE_SCREEN_WITH_CURSOR)
        + "the other page"
        + reset_mode(PrivateMode.ALTERNATE_SCREEN_WITH_CURSOR)
    ),
    (csi(escape.CUP, 5, 10) + "late" + csi(escape.IL, 2) + csi(escape.DL, 1)),  # IL and DL under the cursor.
    csi(escape.CUP, 1, 1) + csi(escape.DCH, 3) + csi(escape.ICH, 4),  # DCH and ICH.
    "a line that is much longer than forty columns and wraps twice over",
]


async def test_the_same_rows_come_out_either_way():
    keeping = TerminalApp(backend=NoBackend())
    building = TerminalApp(backend=NoBackend())

    async with keeping.run_test(size=SIZE), building.run_test(size=SIZE):
        one = keeping.query_one(Terminal)
        other = building.query_one(Terminal)

        for number, chunk in enumerate(CHUNKS):
            one.stream.feed(chunk)
            other.stream.feed(chunk)

            kept = frame(one, forget=False)
            built = frame(other, forget=True)
            assert kept == built, "chunk %d (%r)" % (number, chunk[:40])


def through_textual(terminal: Terminal, refresh) -> list[list[tuple[str, Style | None]]]:
    """
    A frame the way Textual draws one: `refresh` names what to draw
    again, and Textual's own line cache answers every row it was not
    told about.
    """
    refresh()
    return [
        [(segment.text, segment.style) for segment in strip] for strip in terminal.render_lines(Region(0, 0, *SIZE))
    ]


async def test_textual_draws_the_same_frames_when_told_only_the_rows_that_changed():
    """
    `refresh_changed` names a row to Textual only when its answer moved.
    A row it misses is a row Textual hands back from its cache, stale. So
    one widget refreshes what changed, one refreshes everything, and
    every frame has to match. Lillecarl/pymux#127.
    """
    naming = TerminalApp(backend=NoBackend())
    everything = TerminalApp(backend=NoBackend())

    async with naming.run_test(size=SIZE) as one_pilot, everything.run_test(size=SIZE) as other_pilot:
        one = naming.query_one(Terminal)
        other = everything.query_one(Terminal)
        # Focused, so the cursor is drawn and moves between rows.
        one.focus()
        other.focus()
        await one_pilot.pause()
        await other_pilot.pause()

        for number, chunk in enumerate([*CHUNKS, csi(escape.CUP, 3, 7), csi(escape.CUP, 9, 2)]):
            one.stream.feed(chunk)
            other.stream.feed(chunk)

            named = through_textual(one, one.refresh_changed)
            whole = through_textual(other, other.refresh)
            assert named == whole, "chunk %d (%r)" % (number, chunk[:40])


async def test_one_written_row_is_the_one_row_textual_asks_for():
    app = TerminalApp(backend=NoBackend())
    async with app.run_test(size=SIZE):
        terminal = app.query_one(Terminal)
        terminal.stream.feed("first\r\nsecond\r\nthird" + csi(escape.CUP, 9, 1))
        through_textual(terminal, terminal.refresh_changed)

        asked = []
        render_line = terminal.render_line

        def counting(y: int) -> Strip:
            asked.append(y)
            return render_line(y)

        terminal.render_line = counting
        terminal.stream.feed(csi(escape.CUP, 2, 1) + "again" + csi(escape.CUP, 9, 1))
        through_textual(terminal, terminal.refresh_changed)
        assert asked == [1]


async def test_a_frame_after_one_row_costs_a_fraction_of_a_whole_frame():
    """
    What the region refresh buys, in instructions: Textual's work per row
    it is asked for is most of a frame, and a row nobody named costs it
    nothing.
    """
    size = (160, 50)
    app = TerminalApp(backend=NoBackend())
    async with app.run_test(size=size):
        terminal = app.query_one(Terminal)

        def frame(refresh) -> None:
            refresh()
            terminal.render_lines(Region(0, 0, *size))

        terminal.stream.feed("".join("row %d\r\n" % n for n in range(size[1] - 1)))
        frame(terminal.refresh)

        terminal.stream.feed(csi(escape.CUP, 2, 1) + "again" + csi(escape.CUP, 9, 1))
        named = count_instructions(lambda: frame(terminal.refresh_changed))
        terminal.stream.feed(csi(escape.CUP, 2, 1) + "twice" + csi(escape.CUP, 9, 1))
        whole = count_instructions(lambda: frame(terminal.refresh))
        assert named * 3 < whole, (named, whole)


async def test_a_row_that_nothing_wrote_is_the_object_that_was_drawn():
    "The point of the whole thing: it is not built a second time."
    app = TerminalApp(backend=NoBackend())
    async with app.run_test(size=SIZE):
        terminal = app.query_one(Terminal)
        terminal.stream.feed("first\r\nsecond\r\nthird")

        once = terminal.render_line(0)
        assert terminal.render_line(0) is once


async def test_a_row_that_was_written_is_built_again():
    app = TerminalApp(backend=NoBackend())
    async with app.run_test(size=SIZE):
        terminal = app.query_one(Terminal)
        terminal.stream.feed("first\r\nsecond")

        once = terminal.render_line(0)
        # The cursor leaves the row afterwards, because the row it
        # stands on is never kept.
        terminal.stream.feed(csi(escape.CUP, 1, 1) + "again" + csi(escape.CUP, 5, 1))
        again = terminal.render_line(0)
        assert again is not once
        assert terminal.render_line(0) is again


async def test_the_row_the_cursor_stands_on_is_never_kept():
    """
    It is the one row whose answer depends on something outside it: a
    focused pane draws the cursor by reversing the cell it stands on.
    """
    app = TerminalApp(backend=NoBackend())
    async with app.run_test(size=SIZE) as pilot:
        terminal = app.query_one(Terminal)
        terminal.focus()
        await pilot.pause()

        terminal.stream.feed("hello")
        with_the_cursor = frame(terminal, forget=False)

        # The cursor moves along a row that nothing writes to.
        terminal.stream.feed(csi(escape.CUP, 1, 20))
        assert frame(terminal, forget=False) == frame(terminal, forget=True)
        assert frame(terminal, forget=False) != with_the_cursor
