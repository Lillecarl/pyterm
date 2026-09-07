"""
How Rich spells what a cell carries.

A screen holds an `Appearance`: the rendition that SGR set, and the
hyperlink that "OSC 8" opened. Both are a model, and neither is a
spelling. What a renderer writes for them is the renderer's own answer,
and this file is Rich's.

`ptterm/style.py` is the same file for prompt_toolkit, and the two share
no word. That is the whole argument of Lillecarl/pymux#82: a cell used
to hold a style string, so a cell held one renderer's spelling, and a
second front end could not exist.

**Three things a `Rendition` holds do not reach Rich.** They are not
dropped by the screen: a program can still ask for them back, and
prompt_toolkit draws two of the three. Rich has no field for them.

- The shape of an underline. Rich draws a single line (`underline`) and
  a double one (`underline2`), so "curly", "dotted" and "dashed" all
  draw as a single line.
- The colour of that underline. Rich colours the text and the ground
  and nothing else.
- The baseline. Rich has no superscript and no subscript.

`hyperlink_id` goes the same way: Rich carries the target of a link and
not the id that joins its pieces.
"""
from functools import lru_cache
from typing import TYPE_CHECKING, Any, Dict

from pyte.colors import SgrColor
from rich.color import Color
from rich.color_triplet import ColorTriplet
from rich.style import Style

if TYPE_CHECKING:
    from pyte.screen import Appearance

__all__ = ("color_of", "style_of")


def color_of(color: SgrColor) -> Color:
    """
    The Rich colour for one colour of a cell.

    A number of the palette stays a number: a program that asks for one
    asks the terminal of the user to paint it, and that terminal has a
    theme. Rich writes the SGR code back out for such a colour, so the
    theme still decides. A colour that a program named itself becomes a
    triplet, because no theme has an opinion about that one.

    `SgrColor()` with neither is the colour of the terminal by name
    ("SGR 39" and "SGR 49"), which Rich calls the default.
    """
    if color.rgb is not None:
        return Color.from_triplet(ColorTriplet(*color.rgb))
    if color.index is None:
        return Color.default()
    return Color.from_ansi(color.index)


def _spelled(appearance: "Appearance") -> Style:
    """
    The Rich style that draws one cell.

    `style_of` is this function with the answers remembered. Nothing
    calls this one directly.

    Only what a program asked for is set. A field left at `None` is one
    that Rich takes from the style underneath, which is how the widget
    paints its own ground under the cells.
    """
    rendition = appearance.rendition
    fields: Dict[str, Any] = {}

    if rendition.color:
        fields["color"] = color_of(rendition.color)
    if rendition.bgcolor:
        fields["bgcolor"] = color_of(rendition.bgcolor)
    if rendition.bold:
        fields["bold"] = True
    if rendition.dim:
        fields["dim"] = True
    if rendition.italic:
        fields["italic"] = True
    if rendition.underline:
        # Rich knows two of the five shapes. The other three draw as a
        # single line, which is what a terminal that knows none of them
        # does as well.
        if rendition.underline_style == "double":
            fields["underline2"] = True
        else:
            fields["underline"] = True
    if rendition.blink:
        fields["blink"] = True
    if rendition.reverse:
        fields["reverse"] = True
    if rendition.hidden:
        fields["conceal"] = True
    if rendition.strike:
        fields["strike"] = True

    if appearance.hyperlink:
        fields["link"] = appearance.hyperlink

    return Style(**fields)


#: The Rich style that draws one cell.
#:
#: A frame asks this once per cell, so it is the hot path of drawing,
#: and a screen holds a handful of appearances. `lru_cache` answers a
#: hit without running any bytecode at all, which a dictionary of our
#: own cannot: `checks.ptterm-instructions` measured that difference at
#: seven points of a frame for the same call in ptterm.
#:
#: The answers are also the same object every time, which is what lets
#: `render_line` join a run of cells by identity rather than by
#: comparing two styles field by field.
#:
#: The size holds every appearance that a screen can hand out, because
#: `appearance_of` keeps ten thousand.
style_of = lru_cache(maxsize=10 * 1000)(_spelled)
