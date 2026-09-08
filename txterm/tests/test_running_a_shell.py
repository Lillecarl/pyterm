"""
A real program in a real widget, from end to end.

Textual drives itself here: `run_test` gives an application a headless
driver and a pilot that presses keys. What the program writes goes over
a pty, through ptterm's parser, and onto the screen this widget draws.

**Every program below waits at the end instead of exiting.** What a
program writes just before it exits is sometimes lost, because the
reaper closes the pty without draining it (Lillecarl/pymux#121). A test
that ends its program at once is a test that fails once in a dozen runs
for a reason that has nothing to do with what it asks.
"""
import asyncio
import sys

from txterm import Terminal, TerminalApp
from pyte.modes import PrivateMode
from pyte.sequences import set_mode

#: How long a test may wait for a program to say something, in seconds.
TIMEOUT = 5.0

#: How often the loop is turned while waiting.
TICK = 0.01

#: What keeps a program alive after it has said its piece. The test
#: takes the application down, so the number only has to outlive it.
LINGER = "\nimport time\ntime.sleep(30)\n"

#: The size of the pane in every test here.
SIZE = (40, 10)


def program(source: str, linger: bool = True) -> list:
    "A python program, on the interpreter that runs these tests."
    return [sys.executable, "-c", source + (LINGER if linger else "")]


def text_of(terminal: Terminal) -> str:
    "Everything the screen holds, as plain text."
    buffer = terminal.emulator.page.data_buffer
    rows = []
    for y in sorted(buffer):
        row = buffer[y]
        if row:
            rows.append("".join(row[x].char for x in range(max(row) + 1)))
        else:
            rows.append("")
    return "\n".join(rows)


async def until(terminal: Terminal, text: str) -> None:
    "Wait for `text` to turn up on the screen."
    deadline = asyncio.get_event_loop().time() + TIMEOUT
    while text not in text_of(terminal):
        if asyncio.get_event_loop().time() > deadline:
            raise AssertionError(
                "waited %g seconds for %r; the screen holds %r"
                % (TIMEOUT, text, text_of(terminal))
            )
        await asyncio.sleep(TICK)


async def test_what_a_program_writes_reaches_the_screen():
    app = TerminalApp(program("print('hello from the pty')"))
    async with app.run_test(size=SIZE):
        await until(app.query_one(Terminal), "hello from the pty")


async def test_the_program_is_told_how_big_the_pane_is():
    app = TerminalApp(
        program(
            "import os\n"
            "size = os.get_terminal_size()\n"
            "print('SIZE %d %d' % (size.columns, size.lines))"
        )
    )
    async with app.run_test(size=SIZE):
        await until(app.query_one(Terminal), "SIZE 40 10")


async def test_a_letter_reaches_the_program():
    app = TerminalApp(program("print('<' + input() + '>')"))
    async with app.run_test(size=SIZE) as pilot:
        terminal = app.query_one(Terminal)
        await pilot.press("p", "i", "n", "g", "enter")
        await until(terminal, "<ping>")


async def test_tab_reaches_the_program():
    """
    Textual gives "tab" to the next widget. A terminal is where the
    program decides what tab means, so the widget stops the key before
    the screen and the app see it.
    """
    app = TerminalApp(
        program("import sys\nprint('GOT %r' % sys.stdin.read(1))")
    )
    async with app.run_test(size=SIZE) as pilot:
        terminal = app.query_one(Terminal)
        await pilot.press("tab", "enter")
        await until(terminal, "GOT '\\t'")


async def test_ctrl_c_reaches_the_program():
    """
    And the same for "ctrl+c", which Textual binds to a help message.
    Here it goes down the pty, and the line discipline turns it into the
    signal that every program in a terminal expects.
    """
    app = TerminalApp(
        program(
            "import signal\n"
            "signal.signal(signal.SIGINT, lambda *_: print('SIGINT', flush=True))\n"
            "print('READY', flush=True)"
        )
    )
    async with app.run_test(size=SIZE) as pilot:
        terminal = app.query_one(Terminal)
        await until(terminal, "READY")
        await pilot.press("ctrl+c")
        await until(terminal, "SIGINT")


async def test_the_arrow_keys_follow_the_mode_of_the_program():
    """
    A program that turns application cursor mode on reads "ESC O A" for
    the up arrow, and one that does not reads "ESC [ A". The widget
    sends the plain sequence and the screen encodes it, because the
    screen is what holds the mode.

    The program reads a whole line, because a pty hands one over a line
    at a time until a program says otherwise.
    """
    app = TerminalApp(
        program(
            "import sys\n"
            # DECCKM on, and then read what the up arrow sends.
            "sys.stdout.write('\\x1b[?1h')\n"
            "sys.stdout.flush()\n"
            "print('READY', flush=True)\n"
            "print('GOT %r' % sys.stdin.readline(), flush=True)"
        )
    )
    async with app.run_test(size=SIZE) as pilot:
        terminal = app.query_one(Terminal)
        await until(terminal, "READY")
        await pilot.press("up", "enter")
        await until(terminal, "GOT '\\x1bOA")


async def test_a_paste_is_bracketed_when_the_program_asked():
    """
    A program that turned bracketed paste on reads the text between two
    markers, so it can tell what a person typed from what they pasted.
    The screen holds that mode, so the screen wraps the text.
    """
    from textual import events

    app = TerminalApp(
        program("import sys\nprint('GOT %r' % sys.stdin.readline(), flush=True)")
    )
    async with app.run_test(size=SIZE) as pilot:
        terminal = app.query_one(Terminal)
        terminal.stream.feed(set_mode(PrivateMode.BRACKETED_PASTE))
        terminal.post_message(events.Paste("ping"))
        await pilot.press("enter")
        await until(terminal, "GOT '\\x1b[200~ping\\x1b[201~")


async def test_the_end_of_a_program_reaches_the_application():
    "The widget says so, and an application decides what that means."

    class Watching(TerminalApp):
        def __init__(self, command) -> None:
            super().__init__(command)
            self.ended = asyncio.Event()

        def on_terminal_exited(self, event) -> None:
            self.ended.set()

    app = Watching(program("pass", linger=False))
    async with app.run_test(size=SIZE):
        await asyncio.wait_for(app.ended.wait(), TIMEOUT)
