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
from no_backend import NoBackend
from txterm import Terminal, TerminalApp
from pyte import escape
from pyte.modes import PrivateMode
from pyte.sequences import csi, reset_mode
from pyte.sequences import Sharp, sharp
from pyte.sequences import set_mode

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
    return [
        [(segment.text, segment.style) for segment in terminal.render_line(y)]
        for y in range(LINES)
    ]


#: What a real program does, in the shapes that move rows about. Each
#: one is fed to both widgets, and a frame is taken after each.
CHUNKS = [
    "the first line\r\nthe second\r\nthe third",
    csi(escape.CUP, 1, 1) + "over the first",
    csi(escape.SGR, 7) + "reversed" + csi(escape.SGR, 0) + " and not",
    "\r\n" * 12,                    # Scroll a long way.
    csi(escape.DECSTBM, 2, 4) + csi(escape.CUP, 3, 1) + "inside a region\r\n\r\n\r\n",
    csi(escape.DECSTBM),                       # And the region away again.
    csi(escape.CUP) + csi(escape.ED, 2),                # Clear the screen.
    sharp(Sharp.DECALN),                       # DECALN: fill it with E.
    set_mode(PrivateMode.REVERSE_VIDEO),                     # DECSCNM: reverse the whole screen.
    "more text after the reverse",
    reset_mode(PrivateMode.REVERSE_VIDEO),
    (
        set_mode(PrivateMode.ALTERNATE_SCREEN_WITH_CURSOR)
        + "the other page"
        + reset_mode(PrivateMode.ALTERNATE_SCREEN_WITH_CURSOR)
    ),
    (
        csi(escape.CUP, 5, 10)
        + "late"
        + csi(escape.IL, 2)
        + csi(escape.DL, 1)
    ),  # IL and DL under the cursor.
    csi(escape.CUP, 1, 1) + csi(escape.DCH, 3) + csi(escape.ICH, 4),      # DCH and ICH.
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
