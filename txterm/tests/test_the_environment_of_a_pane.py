"""
What a program started by this widget finds in its environment.

The widget owns a screen and a `Process`. It is therefore the only
layer that can say the two things a program has to be told: that it
draws on this screen and not on the terminal the application runs in,
and where the entry that describes this screen lives. `pyte` has no
child to set an environment for, and `ptyhost` runs a program and has
no opinion on what parses the bytes. Lillecarl/pymux#125.

**The child asks ncurses, and not the environment.** `curses.setupterm`
reads `TERM` and looks the entry up in the database. A program that
gets that far has found a real entry, which is the thing that matters:
naming an entry that is not installed is worse than naming xterm.
"""
from pyte.screen import TERMINAL_NAME
from txterm import Terminal, TerminalApp

from test_running_a_shell import SIZE, program, until


async def test_a_program_is_told_the_name_of_this_screen(monkeypatch):
    "And not the name of the terminal that the tests themselves run in."
    monkeypatch.setenv("TERM", "the-outer-terminal")
    app = TerminalApp(program("import os\nprint('TERM=' + os.environ['TERM'])"))
    async with app.run_test(size=SIZE):
        await until(app.query_one(Terminal), "TERM=" + TERMINAL_NAME)


async def test_ncurses_finds_the_entry_that_the_program_is_told_about():
    """
    `setupterm` raises when it cannot find the entry that `TERM` names,
    so a program that gets a number back has been through the database.
    The name goes in the answer as well: 256 colours is what the
    fallback says too, and the pair is what only the real entry gives.
    """
    app = TerminalApp(
        program(
            "import curses, os\n"
            "curses.setupterm()\n"
            "print('FOUND=%s:%d'"
            " % (os.environ['TERM'], curses.tigetnum('colors')))"
        )
    )
    async with app.run_test(size=SIZE):
        await until(app.query_one(Terminal), "FOUND=%s:256" % TERMINAL_NAME)


async def test_a_program_may_write_a_colour():
    """
    Without this a program falls back to the palette of `TERM` and
    quantises a 24 bit colour to an index before this screen sees it.
    """
    app = TerminalApp(
        program("import os\nprint('DEPTH=' + os.environ['COLORTERM'])")
    )
    async with app.run_test(size=SIZE):
        await until(app.query_one(Terminal), "DEPTH=truecolor")


async def test_the_name_of_the_outer_terminal_is_gone(monkeypatch):
    """
    A file manager that finds `KITTY_WINDOW_ID` draws its previews with
    the unicode placeholders of kitty, which this screen does not draw.
    """
    monkeypatch.setenv("KITTY_WINDOW_ID", "1")
    app = TerminalApp(
        program(
            "import os\n"
            "print('KITTY=[%s]' % os.environ.get('KITTY_WINDOW_ID', ''))"
        )
    )
    async with app.run_test(size=SIZE):
        await until(app.query_one(Terminal), "KITTY=[]")


async def test_the_rest_of_the_environment_reaches_the_program(monkeypatch):
    monkeypatch.setenv("A_VARIABLE_OF_THE_USER", "kept")
    app = TerminalApp(
        program("import os\nprint('KEPT=' + os.environ['A_VARIABLE_OF_THE_USER'])")
    )
    async with app.run_test(size=SIZE):
        await until(app.query_one(Terminal), "KEPT=kept")
