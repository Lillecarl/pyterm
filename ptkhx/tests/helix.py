"""
Real Helix on a pty, read back in Helix's own test notation.

`run` starts `hx` on a file holding a case's text, puts the case's
selection on it with keys, sends the case's keys, and reads the screen
through pyte. A theme of its own gives each kind of cell a colour no
other has: the primary selection, the other selections, and the cursor
of each. Then the text comes from the file `:w` writes.

Helix draws each range by its cells, so a range one cell wide shows no
direction: `#[a|]#` and `#[|a]#` draw the same. `seen` reduces both
sides to what Helix draws before they are compared.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from pathlib import Path
from typing import Final

import anyio
from ptyhost import Process
from ptyhost.backends.posix import PosixBackend, spawn_of
from pyte.screen import Screen
from pyte.streams import Stream

from ptkhx import Mode, Selection
from ptkhx.keys import parse_keys
from ptkhx.testing import parse_annotated

__all__ = ["Seen", "annotate", "run", "seen"]

COLUMNS: Final = 80
LINES: Final = 24

#: The background of each kind of cell, in the theme below.
PRIMARY_SELECTION: Final = (0, 160, 0)
SELECTION: Final = (0, 0, 160)
PRIMARY_CURSOR: Final = (160, 160, 0)
CURSOR: Final = (160, 0, 0)
#: The bracket that matches the one under a cursor. Helix looks a scope
#: up by its parents, so without a colour of its own it drew as a cursor.
MATCH: Final = (1, 2, 3)

#: How long the screen must stay still before it counts as drawn.
QUIET_SECONDS: Final = 0.3
#: Between two keys: an escape and the key after it would read as Alt.
KEY_GAP_SECONDS: Final = 0.03
DEADLINE_SECONDS: Final = 10.0

CONFIG: Final = """\
theme = "oracle"

[editor]
gutters = []
auto-pairs = false
auto-completion = false
auto-format = false
auto-info = false
cursorline = false
color-modes = false
true-color = true
insert-final-newline = false
trim-trailing-whitespace = false

[editor.lsp]
enable = false

[editor.indent-guides]
render = false
"""


def _hex(rgb: tuple[int, int, int]) -> str:
    return "#%02x%02x%02x" % rgb


THEME: Final = "\n".join(
    [
        '"ui.selection" = { bg = "%s" }' % _hex(SELECTION),
        '"ui.selection.primary" = { bg = "%s" }' % _hex(PRIMARY_SELECTION),
        '"ui.cursor.match" = { bg = "%s" }' % _hex(MATCH),
        *('"ui.cursor%s" = { bg = "%s" }' % (suffix, _hex(CURSOR)) for suffix in ("", ".normal", ".select", ".insert")),
        *(
            '"ui.cursor.primary%s" = { bg = "%s" }' % (suffix, _hex(PRIMARY_CURSOR))
            for suffix in ("", ".normal", ".select", ".insert")
        ),
    ]
)

_NAMED: Final = {
    "<esc>": "\x1b",
    "<ret>": "\r",
    "<tab>": "\t",
    "<backspace>": "\x7f",
    "<del>": "\x1b[3~",
    "<up>": "\x1b[A",
    "<down>": "\x1b[B",
    "<right>": "\x1b[C",
    "<left>": "\x1b[D",
    "<home>": "\x1b[H",
    "<end>": "\x1b[F",
    "<pageup>": "\x1b[5~",
    "<pagedown>": "\x1b[6~",
}

_MODES: Final = {"NOR": Mode.NORMAL, "INS": Mode.INSERT, "SEL": Mode.SELECT}


def key_bytes(token: str) -> str:
    "What a terminal sends for one canonical key token."
    if token in _NAMED:
        return _NAMED[token]
    if token.startswith("<A-"):
        return "\x1b" + key_bytes(token[3:-1])
    if token.startswith("<C-"):
        return chr(ord(token[3:-1]) & 0x1F)
    return token


@dataclass(frozen=True)
class Seen:
    "What Helix draws: the text, the mode, and each range as its cells."

    text: str
    mode: Mode
    #: `(start, end, cursor, primary)` for each range, in document order.
    ranges: tuple[tuple[int, int, int, bool], ...]


def seen(text: str, selection: Selection, mode: Mode) -> Seen:
    "What Helix would draw for this state, for a state ptkhx holds."
    ranges = []
    for index, rng in enumerate(selection):
        cursor = rng.cursor(text)
        start, end = rng.start, max(rng.end, rng.start + 1)
        ranges.append((start, max(end, cursor + 1), cursor, index == selection.primary_index))
    return Seen(text, mode, tuple(ranges))


def annotate(drawn: Seen) -> str:
    """
    What Helix draws, in its notation, with the mode in front. A range
    one cell wide is written forwards: the screen shows no direction.
    """
    out, at = [], 0
    for start, end, cursor, primary in drawn.ranges:
        opener, closer = ("#[", "]#") if primary else ("#(", ")#")
        content = drawn.text[start:end]
        out.append(drawn.text[at:start])
        if cursor == start and end - start > 1:
            out.append("%s|%s%s" % (opener, content, closer))
        else:
            out.append("%s%s|%s" % (opener, content, closer))
        at = end
    out.append(drawn.text[at:])
    return "%s %s" % (drawn.mode.label, "".join(out))


def setup_keys(selection: Selection) -> str:
    """
    Keys that put one range on a fresh Helix, which opens on the first
    character. `l` crosses a line's end, so a count of it reaches any
    offset.
    """
    if len(selection.ranges) != 1:
        raise ValueError("the oracle sets up one range")
    rng = selection.primary
    if rng.end - rng.start <= 1:
        cursor = rng.start
        return "%dl" % cursor if cursor else ""
    if rng.head > rng.anchor:
        first, last, step = rng.anchor, rng.head - 1, "l"
    else:
        first, last, step = rng.anchor - 1, rng.head, "h"
    moves = ("%dl" % first) if first else ""
    return "%sv%d%sv" % (moves, abs(last - first), step)


class _Helix:
    def __init__(self, command: list[str], environment: dict[str, str]) -> None:
        self.screen = Screen(LINES, COLUMNS, write_process_input=lambda data: self.process.write_input(data))
        self.stream = Stream(self.screen)
        self.last_output = time.monotonic()
        self.ended = anyio.Event()
        backend = PosixBackend(spawn_of(command, environment=lambda env: env.update(environment)))
        self.process = Process(backend=backend, receive=self._receive, done_callback=self.ended.set)
        self.process.set_size(COLUMNS, LINES)

    def _receive(self, data: str) -> None:
        self.last_output = time.monotonic()
        self.stream.feed(data)

    async def quiet(self) -> None:
        with anyio.fail_after(DEADLINE_SECONDS):
            while time.monotonic() - self.last_output < QUIET_SECONDS:
                await anyio.sleep(0.05)

    async def send(self, keys: str) -> None:
        for token in parse_keys(keys):
            self.process.write_input(key_bytes(token))
            await anyio.sleep(KEY_GAP_SECONDS)

    def cell(self, row: int, column: int):
        return self.screen.page.data_buffer[self.screen.line_offset + row][column]

    def background(self, row: int, column: int) -> tuple[int, int, int] | None:
        color = self.cell(row, column).appearance.rendition.bgcolor
        if color is None or color.rgb is None:
            return None
        return tuple(color.rgb)[:3]

    def mode(self) -> Mode:
        status = "".join(self.cell(LINES - 2, column).char or " " for column in range(6))
        for label, mode in _MODES.items():
            if label in status:
                return mode
        raise AssertionError("no mode in Helix's statusline: %r" % (status,))


def _offset(text: str, row: int, column: int) -> int | None:
    "The offset a cell draws, or None for a cell past the line."
    lines = text.split("\n")
    if row >= len(lines):
        return None
    if column > len(lines[row]):
        return None
    return sum(len(line) + 1 for line in lines[:row]) + column


#: Each colour of the theme, as whether it is a cursor and whether it is
#: the primary's.
_KINDS: Final = {
    PRIMARY_SELECTION: (False, True),
    SELECTION: (False, False),
    PRIMARY_CURSOR: (True, True),
    CURSOR: (True, False),
}


def _marks(helix: _Helix) -> dict[tuple[int, int], tuple[bool, bool]]:
    "The cells of the document area that the theme marks, by row and column."
    marks = {}
    for row in range(LINES - 2):
        for column in range(COLUMNS):
            kind = _KINDS.get(helix.background(row, column))
            if kind is not None:
                marks[row, column] = kind
    return marks


def _ranges(marks: dict[tuple[int, int], tuple[bool, bool]], text: str) -> tuple[tuple[int, int, int, bool], ...]:
    "Each run of marked cells, with its cursor, as offsets into `text`."
    marked: list[tuple[int, bool, bool]] = []
    for (row, column), kind in marks.items():
        offset = _offset(text, row, column)
        if offset is not None:
            marked.append((offset, *kind))
    ranges = []
    for offset, is_cursor, primary in sorted(marked):
        last = ranges[-1] if ranges else None
        if last is not None and last[1] == offset and last[3] == primary and not (is_cursor and last[2] is not None):
            ranges[-1] = [last[0], offset + 1, offset if is_cursor else last[2], primary]
        else:
            ranges.append([offset, offset + 1, offset if is_cursor else None, primary])
    return tuple((start, end, start if cursor is None else cursor, primary) for start, end, cursor, primary in ranges)


async def run(annotated: str, keys: str, home: Path) -> Seen:
    "Run `keys` in real Helix on the case `annotated`, and read back what it draws."
    text, selection = parse_annotated(annotated)
    config = home / "config" / "helix"
    (config / "themes").mkdir(parents=True, exist_ok=True)
    (config / "config.toml").write_text(CONFIG)
    (config / "themes" / "oracle.toml").write_text(THEME + "\n")
    document = home / "case.txt"
    document.write_text(text)
    environment = {
        "HOME": str(home),
        "XDG_CONFIG_HOME": str(home / "config"),
        "XDG_CACHE_HOME": str(home / "cache"),
        "XDG_DATA_HOME": str(home / "data"),
        "TERM": "xterm-256color",
        "COLORTERM": "truecolor",
    }
    helix = _Helix(["hx", str(document)], environment)
    async with anyio.create_task_group() as tasks:
        await helix.process.start(tasks)
        await helix.quiet()
        await helix.send(setup_keys(selection))
        await helix.send(keys)
        await helix.quiet()
        mode = helix.mode()
        marks = _marks(helix)
        # The text is the file's: the screen cannot tell a trailing space
        # from an empty cell.
        await helix.send("<esc>:w!<ret>")
        await helix.quiet()
        written = document.read_text()
        await helix.send(":q!<ret>")
        with anyio.move_on_after(DEADLINE_SECONDS):
            await helix.ended.wait()
        if not helix.ended.is_set():
            helix.process.kill()
        tasks.cancel_scope.cancel()
    return Seen(written, mode, _ranges(marks, written))
