"""
A terminal in a Textual widget.

It runs a program on a pty, feeds what the program writes to a screen,
and draws that screen. Three packages do the work, and this file is only
the joint between them:

- `ptyhost` runs the program. It parses nothing.
- `pyte.screen` parses and holds the cells. It draws nothing, and it
  imports no toolkit.
- `txterm.style` says how Rich spells a cell, and `txterm.keys` what a
  key of Textual sends.

`ptterm/terminal.py` is the same joint for prompt_toolkit. Neither reads
a word of the other, which is what Lillecarl/pymux#82 asks for.
"""

import os
import sys
from functools import lru_cache
from typing import Callable, Dict, List, Optional

from pyte.environment import prepare
from pyte.images import ASSUMED_CELL_HEIGHT, ASSUMED_CELL_WIDTH
from pyte.placeholders import PLACEHOLDER
from pyte.cells import PLAIN_APPEARANCE, Cell, appearance_of
from pyte.screen import Screen
from pyte.streams import Stream
from ptyhost import Process
from ptyhost.backends import Backend
from rich.segment import Segment
from rich.style import Style
from textual import events
from textual.message import Message
from textual.strip import Strip
from textual.widget import Widget

from .keys import data_of
from .style import style_of

__all__ = ["Terminal"]

#: Reversed, and not reversed. Three things reverse a cell and each one
#: turns the last: "SGR 7" on the cell, DECSCNM over the whole screen,
#: and the cursor standing on it. libvterm calls that an xor and it is
#: the same answer here.
_REVERSE = Style(reverse=True)
_NOT_REVERSE = Style(reverse=False)

#: The characters that must not reach the terminal of the user as they
#: stand: the C0 controls, delete, and the C1 controls. The parser eats
#: all of these, so one in a cell is a fault here; drawing it would let
#: the terminal of the user read it as a control of its own, and the
#: screen after that is anybody's guess.
_NOT_FOR_A_SCREEN = frozenset(
    chr(code) for code in list(range(0x20)) + [0x7F] + list(range(0x80, 0xA0))
)


#: The size is `style_of`'s, because a key here is one of its answers:
#: a style comes from an appearance, and `pyte.cells` keeps only so
#: many of those alive. The two turnings double it.
@lru_cache(maxsize=2 * appearance_of.size)
def _turned(style: Style, reverse: bool) -> Style:
    """
    One style with the reverse decided.

    The answers are remembered, so a run of cells that all turn the same
    way is still one object and `render_line` joins it by identity.
    """
    return style + (_REVERSE if reverse else _NOT_REVERSE)


def _visible_char(char: str) -> str:
    """
    What to draw for a cell.

    A unicode placeholder stands for a cell of an image, and the
    embedder draws the image itself. The character must not reach the
    screen: a terminal that does not know it paints a box, and the
    combining characters that carry the row and the column pile up on
    top of it. A space keeps the cell.

    The second half of a double width character is an empty string, and
    it goes through as one: the first half is two cells wide already, so
    the two together take the room they should.
    """
    if char.startswith(PLACEHOLDER):
        return " "
    if char in _NOT_FOR_A_SCREEN:
        return " "
    return char


def _in_the_child(
    before_exec_func: Optional[Callable[[], None]],
) -> Callable[[], None]:
    """
    What runs in the child, between the fork and the exec.

    The program runs on the screen of this widget and not in the
    terminal that the application itself runs in, so the environment
    has to say which one it is. Nothing else knows both: `pyte` has no
    child to set an environment for, and `ptyhost` runs a program and
    has no opinion on what parses the bytes. This widget owns a screen
    and a `Process`, so this is the layer. Lillecarl/pymux#125.

    The hook of the caller runs last, so an embedder can still say
    something different.
    """

    def hook() -> None:
        prepare(os.environ)
        if before_exec_func is not None:
            before_exec_func()

    return hook


def create_backend(
    command: List[str], before_exec_func: Optional[Callable[[], None]] = None
) -> Backend:
    "A pty running `command`, for the platform this is."
    if sys.platform.startswith("win"):
        from ptyhost.backends.win32 import Win32Backend

        return Win32Backend()

    from ptyhost.backends.posix import PosixBackend

    # The size of a cell goes into the size of the pty, so that a
    # program that draws images reads the same answer there as
    # "CSI 16 t" gives it. The screen holds that number, so the screen
    # passes it down and the pty layer claims nothing about pixels.
    return PosixBackend.from_command(
        command,
        before_exec_func=_in_the_child(before_exec_func),
        cell=(ASSUMED_CELL_WIDTH, ASSUMED_CELL_HEIGHT),
    )


class Terminal(Widget, can_focus=True):
    """
    A program on a pty, drawn in a Textual widget.

    :param command: The program and its arguments.
    :param before_exec_func: Called in the child, right before `exec`.
    :param backend: A pty of your own. `command` is ignored when this is
        given, which is how a test drives the widget with no child.
    :param bell_func: Called when the program rings the bell.
    :param osc_func: Called with the code and the payload of an OSC
        sequence that only the terminal of the user can serve. (The
        clipboard, a notification, the shape of the pointer.)
    :param resize_func: Called with the lines and the columns that the
        program asks for, when it sends DECSLPP or a window resize.
        Either one is None when the program leaves that side alone. A
        widget cannot take room from the widgets beside it, so whoever
        laid it out decides.
    :param may_resize: Returns whether that ask would be granted. The
        private modes that only exist where a program can have a
        different page go away when it says no, so a program learns at
        once instead of laying its output out for room it will not get.
        **The default is no**, because a widget in a layout cannot
        resize itself; an application that will move the widget passes
        something that says yes.
    :param get_history_limit: Returns how many rows of scrollback this
        widget keeps. The default is two thousand, which is what tmux
        keeps. It is a function and not a number, so the option can
        change while the program runs.
    """

    DEFAULT_CSS = """
    Terminal {
        width: 1fr;
        height: 1fr;
    }
    """

    class Exited(Message):
        "The program in a terminal has ended."

        def __init__(self, terminal: "Terminal") -> None:
            super().__init__()
            self.terminal = terminal

        @property
        def control(self) -> "Terminal":
            return self.terminal

    def __init__(
        self,
        command: Optional[List[str]] = None,
        *,
        before_exec_func: Optional[Callable[[], None]] = None,
        backend: Optional[Backend] = None,
        bell_func: Optional[Callable[[], None]] = None,
        osc_func: Optional[Callable[[str, str], None]] = None,
        resize_func: Optional[Callable[[Optional[int], Optional[int]], None]] = None,
        may_resize: Optional[Callable[[], bool]] = None,
        get_history_limit: Optional[Callable[[], int]] = None,
        name: Optional[str] = None,
        id: Optional[str] = None,
        classes: Optional[str] = None,
    ) -> None:
        super().__init__(name=name, id=id, classes=classes)

        self._backend = backend or create_backend(
            command or ["/bin/bash"], before_exec_func
        )

        # The screen belongs to the front end and not to the pty: a
        # `Process` runs a program and pumps its bytes, and what those
        # bytes mean is decided here. Lillecarl/pymux#85.
        #
        # It is not called `screen`, because `Widget.screen` is the
        # Textual screen this widget is on.
        self.emulator = Screen(
            0,
            0,
            write_process_input=lambda data: self.process.write_input(data),
            bell_func=bell_func,
            osc_func=osc_func,
            resize_func=resize_func,
            # A widget sits in a layout that somebody else owns, so it
            # cannot take room from its neighbours. Saying no is the
            # truth for every widget that nobody has promised to move.
            may_resize=may_resize or (lambda: False),
            # How deep the scrollback goes. The application decides,
            # because it is the application that offers the option. It
            # is a function, so `Screen` reads it on every prune and a
            # change reaches a widget that is already running.
            get_history_limit=get_history_limit,
        )
        self.stream = Stream(self.emulator)
        self.stream.attach(self.emulator)

        #: The pty. It needs a running event loop, so it is made when
        #: the widget mounts and not when it is built.
        self._process: Optional[Process] = None

        #: What this widget drew for each row of the page, and the write
        #: count of the screen that it drew it at. A row whose count has
        #: not moved is a row it does not build again.
        #:
        #: The state is here and not on the screen, because a screen has
        #: more than one reader and no way to know how many: `ptterm`
        #: draws the same screen with prompt_toolkit, and pymux gives
        #: several clients one pane. Lillecarl/pymux#126.
        self._drawn: Dict[int, Strip] = {}
        self._drawn_at: Dict[int, int] = {}

        #: What every remembered row was drawn under. None of it belongs
        #: to a row, so a change to any of it empties the whole memory.
        self._drawn_under: Optional[tuple] = None

        #: Whether the program has been forked yet.
        #:
        #: Not `_running`: Textual keeps the state of the message pump
        #: of every widget under that name, and it is true from the
        #: moment the widget mounts. A terminal that read it would
        #: never start its program and would draw an empty screen for
        #: ever, with nothing to say why.
        self._program_started = False

    @property
    def process(self) -> Process:
        "The program in this widget. It exists once the widget mounts."
        if self._process is None:
            raise RuntimeError("this terminal has not been mounted yet")
        return self._process

    # -- the life of the program ------------------------------------------

    def on_mount(self) -> None:
        self._process = Process(
            backend=self._backend,
            receive=self.stream.feed,
            invalidate=self.refresh,
            done_callback=lambda: self.post_message(self.Exited(self)),
            # A pane that nobody is looking at parses when the loop has
            # nothing better to do. Focus is what "looking at" means.
            has_priority=lambda: self.has_focus,
        )
        self._start(*self.size)

    def on_unmount(self) -> None:
        if self._process is not None:
            self._process.kill()

    def on_resize(self, event: events.Resize) -> None:
        """
        The pane changed size.

        **`self.size` and not `event.size`.** The event carries the
        whole region the widget was given, and `render_line` draws the
        content area inside it. A border of one takes a column on each
        side and a row above and below, so a pty told the outer number
        would give a program two columns and two rows that no frame
        ever draws.
        """
        self._start(*self.size)

    def _start(self, width: int, height: int) -> None:
        """
        Tell the pty and the screen how big the pane is, and start the
        program the first time there is a size to start it on.

        **The size comes before the start.** The child writes as soon as
        it is forked, so a program that draws before a resize reaches it
        would draw at the wrong width. `Process.start` says the same.
        """
        if self._process is None or width <= 0 or height <= 0:
            return

        self._process.set_size(width, height)
        self.emulator.resize(lines=height, columns=width)
        self.emulator.lines = height
        self.emulator.columns = width

        if not self._program_started:
            self._process.start()
            self._program_started = True

    # -- what the user types ----------------------------------------------

    def on_key(self, event: events.Key) -> None:
        """
        Send the key to the program.

        Every key goes, and none of them is a binding of the app: a
        terminal is where "tab" and "ctrl+c" mean what the program in it
        says they mean. `event.stop` keeps the key from bubbling up to
        the screen and the app, which is where those bindings live.

        `Terminal` cannot stop the two bindings that Textual checks
        before the focused widget sees a key at all. An app that hosts
        one of these has to clear them itself; `txterm.app` does.
        """
        event.stop()
        event.prevent_default()

        data = data_of(event)
        if data:
            self.process.write_input(self.emulator.encode_key(data))

    def on_paste(self, event: events.Paste) -> None:
        "Hand pasted text over, bracketed when the program asked for it."
        event.stop()
        event.prevent_default()
        self.process.write_input(self.emulator.wrap_paste(event.text))

    # -- drawing ------------------------------------------------------------

    def _cursor_column(self, y: int) -> Optional[int]:
        """
        The column the cursor stands on in row `y` of the page, or None
        when the cursor is not on that row.

        A pane that is not focused draws no cursor. Several panes each
        drawing one would say that the keyboard reaches all of them.

        The column is the one the cursor stands on, and never the one it
        waits to wrap into: `reported_column` is the same fold that a
        program reads with DSR, so the cursor is drawn where the program
        is told it stands.
        """
        emulator = self.emulator
        if not emulator.page.show_cursor or not self.has_focus:
            return None
        if emulator.pt_cursor_position.y - emulator.line_offset != y:
            return None
        return emulator.reported_column

    #: How many rows this widget remembers having drawn. The history
    #: grows and the rows that leave it never come back, so what is
    #: remembered of them is dead weight. Emptying the whole of it costs
    #: one frame, and a frame is what this saves thousands of.
    #:
    #: Ten thousand is a scrollback depth that people configure: tmux
    #: keeps two thousand by default and kitty is commonly set to fifty
    #: thousand, so `ptterm/tests/measure_instructions.py` measures at
    #: 2000, 10000 and 50000. Under this depth the map holds a whole
    #: history and is never emptied. Over it, a person who scrolls the
    #: whole way pays one frame each time it fills, which is the trade
    #: this number picks.
    _REMEMBER_AT_MOST = 10 * 1000

    def render_line(self, y: int) -> Strip:
        """
        One row of the page, as Rich segments.

        A row is a run of cells that draw the same way, so the segments
        are those runs and not the cells: a frame of eighty by
        twenty-four is two thousand cells and, for most programs, a few
        dozen runs. `style_of` hands the same object back for the same
        appearance, so joining a run is an identity test.

        **A row is built once and kept until the screen writes it
        again.** The screen counts every write it makes to a row, and
        this widget keeps the count it drew each row at, so a frame
        after a program wrote one line draws one line.
        Lillecarl/pymux#126.
        """
        emulator = self.emulator
        width = self.size.width
        if width <= 0:
            return Strip.blank(0)

        # DECSCNM, the width of the pane and the style the widget paints
        # under a row all reach every row and belong to none of them.
        ground = self.visual_style.rich_style
        under = (width, emulator.has_reverse_video, ground)
        if under != self._drawn_under:
            self._drawn.clear()
            self._drawn_at.clear()
            self._drawn_under = under
        elif len(self._drawn) > self._REMEMBER_AT_MOST:
            self._drawn.clear()
            self._drawn_at.clear()

        # The bottom of the screen is what a pane shows. `line_offset`
        # is the first row of it, and the buffer above that is the
        # history.
        number = emulator.line_offset + y
        cursor_column = self._cursor_column(y)
        if cursor_column is None:
            # The row the cursor stands on is the one row whose answer
            # depends on something outside it, so it is never kept.
            # A row with no count of its own carries the one that
            # `touch_everything` last set, so a reset or a page swap
            # moves every row at once and costs nothing to say.
            version = emulator.written_at.get(number, emulator.everything_at)
            if self._drawn_at.get(number) == version:
                return self._drawn[number]
        else:
            version = None

        strip = self._build(number, width, cursor_column, ground)
        if version is not None:
            self._drawn[number] = strip
            self._drawn_at[number] = version
        return strip

    def _build(
        self,
        number: int,
        width: int,
        cursor_column: Optional[int],
        ground: Style,
    ) -> Strip:
        "One row of the page, built from its cells."
        emulator = self.emulator
        row: Dict[int, Cell] = emulator.page.data_buffer.get(number, {})
        # DECSCNM reverses the whole screen: every cell of it, and the
        # blank ones as well.
        reverse_video = emulator.has_reverse_video

        segments: List[Segment] = []
        text: List[str] = []
        current: Optional[Style] = None

        for column in range(width):
            cell = row.get(column)
            if cell is None:
                char = " "
                appearance = PLAIN_APPEARANCE
            elif column == width - 1 and cell.width > 1:
                # A double width character cannot stand in the last
                # column: its second half would be a column the row does
                # not have, and the strip would be one cell too wide.
                char = " "
                appearance = cell.appearance
            else:
                char = _visible_char(cell.char)
                appearance = cell.appearance

            style = style_of(appearance)
            reverse = (
                appearance.rendition.reverse ^ reverse_video ^ (column == cursor_column)
            )
            if reverse != appearance.rendition.reverse:
                style = _turned(style, reverse)

            if style is not current:
                if text:
                    segments.append(Segment("".join(text), current))
                    text = []
                current = style
            text.append(char)

        if text:
            segments.append(Segment("".join(text), current))

        # The style of the widget goes underneath, and the style of a
        # cell over it. A cell says only what a program asked for, so
        # everything else is the ground the widget paints.
        return Strip(segments, width).apply_style(ground)
