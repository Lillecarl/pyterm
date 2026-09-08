"""
What the widget draws, read as the segments it returns.

There is no picture here and no real terminal. `render_line` gives back
a `Strip`, which is the text and the Rich style of every run of cells,
and that is the whole of what txterm decides. The parsing above it is
ptterm's, and its own suite judges that.

Every test feeds the stream by hand, through a backend that starts no
program. Nothing forks.
"""
from no_backend import NoBackend
from rich.color import Color
from rich.style import Style
from txterm import Terminal, TerminalApp
from pyte.modes import PrivateMode
from pyte.sequences import set_mode
from pyte import escape
from pyte.sequences import csi

#: The size of the pane in every test here.
SIZE = (20, 5)


def app_with_a_screen() -> TerminalApp:
    "An application whose terminal runs no program."
    return TerminalApp(backend=NoBackend())


def styles_of(strip):
    "The style of each run of the strip, in order."
    return [segment.style for segment in strip]


async def test_a_program_that_writes_a_word_draws_it():
    app = app_with_a_screen()
    async with app.run_test(size=SIZE):
        terminal = app.query_one(Terminal)
        terminal.stream.feed("hello")
        assert terminal.render_line(0).text == "hello" + " " * 15


async def test_a_row_is_as_wide_as_the_pane():
    "Every row, drawn or not, fills the width. Textual asks for that."
    app = app_with_a_screen()
    async with app.run_test(size=SIZE):
        terminal = app.query_one(Terminal)
        terminal.stream.feed("hi")
        for y in range(SIZE[1]):
            assert terminal.render_line(y).cell_length == SIZE[0]


async def test_cells_that_draw_the_same_way_are_one_segment():
    """
    A frame of eighty by twenty-four is two thousand cells and, for most
    programs, a few dozen runs. The runs are what goes on the wire, so
    the drawing joins them.

    Three here: the plain word, the red one, and the blank rest of the
    row. The cursor is not on this row, so nothing splits.
    """
    app = app_with_a_screen()
    async with app.run_test(size=SIZE):
        terminal = app.query_one(Terminal)
        terminal.stream.feed("ab\x1b[31mcd\x1b[m\r\n")
        assert [segment.text for segment in terminal.render_line(0)] == [
            "ab",
            "cd",
            " " * 16,
        ]


async def test_a_colour_of_the_palette_stays_a_number():
    """
    A program that asks for red asks the terminal of the user to paint
    it, and that terminal has a theme. Rich writes the code back out.
    """
    app = app_with_a_screen()
    async with app.run_test(size=SIZE):
        terminal = app.query_one(Terminal)
        terminal.stream.feed(csi(escape.SGR, 31) + "red" + csi(escape.SGR) + "\r\n")
        red = styles_of(terminal.render_line(0))[0]
        assert red.color == Color.from_ansi(1)


async def test_a_colour_a_program_named_itself_is_a_triplet():
    app = app_with_a_screen()
    async with app.run_test(size=SIZE):
        terminal = app.query_one(Terminal)
        terminal.stream.feed("\x1b[38;2;18;52;86mown\x1b[m\r\n")
        own = styles_of(terminal.render_line(0))[0]
        assert own.color.triplet == (0x12, 0x34, 0x56)


async def test_bold_and_underline_reach_rich():
    app = app_with_a_screen()
    async with app.run_test(size=SIZE):
        terminal = app.query_one(Terminal)
        terminal.stream.feed(csi(escape.SGR, 1, 4) + "loud" + csi(escape.SGR) + "\r\n")
        loud = styles_of(terminal.render_line(0))[0]
        assert loud.bold
        assert loud.underline


async def test_a_double_underline_is_the_one_rich_has():
    "Rich draws two of the five shapes. The double one is one of them."
    app = app_with_a_screen()
    async with app.run_test(size=SIZE):
        terminal = app.query_one(Terminal)
        terminal.stream.feed(csi(escape.SGR, 21) + "twice" + csi(escape.SGR) + "\r\n")
        twice = styles_of(terminal.render_line(0))[0]
        assert twice.underline2


async def test_a_link_travels_as_a_link():
    app = app_with_a_screen()
    async with app.run_test(size=SIZE):
        terminal = app.query_one(Terminal)
        terminal.stream.feed("\x1b]8;;https://example.com\x1b\\here\x1b]8;;\x1b\\\r\n")
        here = styles_of(terminal.render_line(0))[0]
        assert here.link == "https://example.com"


async def test_a_double_width_character_takes_two_columns():
    """
    The second half of one is an empty cell, so the two together take
    the room they should and the row is still as wide as the pane.
    """
    app = app_with_a_screen()
    async with app.run_test(size=SIZE):
        terminal = app.query_one(Terminal)
        terminal.stream.feed("日本")
        strip = terminal.render_line(0)
        assert strip.text.startswith("日本")
        assert strip.cell_length == SIZE[0]


async def test_the_cursor_is_drawn_where_the_program_stands():
    "The focused pane reverses the cell the cursor is on."
    app = app_with_a_screen()
    async with app.run_test(size=SIZE):
        terminal = app.query_one(Terminal)
        terminal.stream.feed("ab")
        segments = list(terminal.render_line(0))
        assert [segment.text for segment in segments] == ["ab", " ", " " * 17]
        assert segments[1].style.reverse


async def test_a_pane_that_is_not_focused_draws_no_cursor():
    """
    Several panes each drawing a cursor would say that the keyboard
    reaches all of them.
    """
    app = app_with_a_screen()
    async with app.run_test(size=SIZE) as pilot:
        terminal = app.query_one(Terminal)
        terminal.blur()
        # Focus travels as a message, so it is a turn of the loop away.
        await pilot.pause()
        terminal.stream.feed("ab")
        # Nothing splits the row, because nothing on it draws
        # differently from the rest.
        assert [segment.text for segment in terminal.render_line(0)] == [
            "ab" + " " * 18
        ]


async def test_a_reversed_cell_under_the_cursor_turns_back():
    """
    Three things reverse a cell and each one turns the last. A cell that
    "SGR 7" already reversed is drawn the plain way under the cursor.
    """
    app = app_with_a_screen()
    async with app.run_test(size=SIZE):
        terminal = app.query_one(Terminal)
        # The cursor stands on the third column, which is reversed.
        terminal.stream.feed("ab" + csi(escape.SGR, 7) + " " + csi(escape.CHA, 3))
        segments = list(terminal.render_line(0))
        assert segments[1].text == " "
        assert not segments[1].style.reverse


async def test_the_whole_screen_reverses_with_decscnm():
    """
    "CSI ? 5 h" reverses the screen, and the screen is more than the
    cells a program wrote: an empty row turns as well.
    """
    app = app_with_a_screen()
    async with app.run_test(size=SIZE):
        terminal = app.query_one(Terminal)
        terminal.stream.feed(set_mode(PrivateMode.REVERSE_VIDEO))
        for style in styles_of(terminal.render_line(4)):
            assert style.reverse


async def test_a_control_character_in_a_cell_draws_as_a_blank():
    """
    The parser eats every control, so one in a cell is a fault here. It
    must not reach the terminal of the user, which would read it as a
    control of its own.
    """
    app = app_with_a_screen()
    async with app.run_test(size=SIZE):
        terminal = app.query_one(Terminal)
        terminal.emulator.draw("\x01")
        assert terminal.render_line(0).text == " " * SIZE[0]


async def test_the_pane_shows_the_bottom_of_the_screen():
    """
    A program that writes more rows than the pane has scrolls, and the
    pane draws the last ones. The rest is history and no row of it is on
    the screen.
    """
    app = app_with_a_screen()
    async with app.run_test(size=SIZE):
        terminal = app.query_one(Terminal)
        terminal.stream.feed("".join("line %d\r\n" % n for n in range(9)))
        assert terminal.render_line(0).text.startswith("line 5")
        assert terminal.render_line(3).text.startswith("line 8")


async def test_the_pty_hears_the_size_of_the_pane():
    "The size goes to the pty before the program starts."
    app = app_with_a_screen()
    async with app.run_test(size=SIZE):
        terminal = app.query_one(Terminal)
        assert terminal._backend.sizes[-1] == SIZE
        assert (terminal.emulator.columns, terminal.emulator.lines) == SIZE


async def test_a_border_is_not_part_of_the_pane():
    """
    A resize carries the whole region the widget was given, and the
    content is what is inside the border. A pty told the outer number
    would give a program two columns and two rows that no frame draws.
    """

    class Framed(TerminalApp):
        CSS = "Terminal { border: solid white; }"

    app = Framed(backend=NoBackend())
    async with app.run_test(size=SIZE):
        terminal = app.query_one(Terminal)
        inside = (SIZE[0] - 2, SIZE[1] - 2)
        assert terminal._backend.sizes[-1] == inside
        assert (terminal.emulator.columns, terminal.emulator.lines) == inside
        assert terminal.render_line(0).cell_length == inside[0]


async def test_the_widget_paints_its_own_ground():
    """
    A cell says only what a program asked for. Everything else comes
    from the style of the widget, so a plain cell is not a style with
    nothing in it.
    """
    app = app_with_a_screen()
    async with app.run_test(size=SIZE):
        terminal = app.query_one(Terminal)
        terminal.stream.feed("plain")
        assert styles_of(terminal.render_line(0))[0] != Style()
