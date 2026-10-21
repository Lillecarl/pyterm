"""
The runs build draws what the cell build drew.

`segments_of_row` maps the runs of `pyte.runs` onto Rich segments. This
holds it against the walk over every cell that it replaced, segment for
segment: styled text, blanks, gaps, combining and wide characters, a
wide character the right edge cuts, the cursor, and reverse video.
Lillecarl/pymux#521.
"""

from __future__ import annotations

import pytest
from pyte.cells import PLAIN_APPEARANCE
from pyte.screen import Screen
from pyte.streams import Stream
from rich.segment import Segment

from txterm.style import style_of
from txterm.terminal import _turned, _visible_char, segments_of_row

SEQUENCES = [
    # Styled words with interior and trailing blanks.
    "\x1b[1;31mhello \x1b[0mworld   \x1b[7mrev\x1b[27m   tail   ",
    # A second row, so a move lands on one.
    "\x1b[2;10H\x1b[32mgreen here\x1b[0m  ",
    # Wide, combining, and an erase past the cursor.
    "\x1b[3;1H⡑ wide é́tail\x1b[3;20H\x1b[K",
    # Sparse writes with gaps between them.
    "\x1b[5;5Hone\x1b[5;40Htwo\x1b[5;70H   ",
    # Trailing blanks a program wrote, spelled so no editor eats them.
    "\x1b[6;1Hleft\x20\x20\x20",
    # Wide characters, so an edge can fall on one.
    "\x1b[8;1Habc 你好漢 def",
]


def _screen(reverse: bool) -> Screen:
    screen = Screen(100, 24, lambda part: None)
    stream = Stream(screen)
    for sequence in SEQUENCES:
        stream.feed(sequence)
    if reverse:
        stream.feed("\x1b[?5h")
    return screen


def _cells(row, width: int, reverse_video: bool, cursor_column: int | None) -> list[Segment]:
    "One row the way one cell at a time built it."
    row = row or {}
    segments: list[Segment] = []
    text: list[str] = []
    current = None
    for column in range(width):
        cell = row.get(column)
        if cell is None:
            char = " "
            appearance = PLAIN_APPEARANCE
        elif column == width - 1 and cell.width > 1:
            char = " "
            appearance = cell.appearance
        else:
            char = _visible_char(cell.char)
            appearance = cell.appearance

        style = style_of(appearance)
        reverse = appearance.rendition.reverse ^ reverse_video ^ (column == cursor_column)
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
    return segments


@pytest.mark.parametrize("reverse", [False, True])
@pytest.mark.parametrize("cursor_column", [None, 0, 4, 6, 12, 99])
@pytest.mark.parametrize("width", [100, 13, 9, 7])
@pytest.mark.parametrize("number", [0, 1, 2, 4, 5, 7, 10])
def test_a_row_built_from_runs_draws_what_cells_drew(number, width, cursor_column, reverse) -> None:
    row = _screen(reverse).page.data_buffer.get(number)

    assert segments_of_row(row, width, reverse, cursor_column) == _cells(row, width, reverse, cursor_column)
