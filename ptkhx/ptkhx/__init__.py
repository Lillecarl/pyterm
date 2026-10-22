"""
Helix's modal editing, for a prompt_toolkit buffer.

`Editor` takes a key at a time and imports nothing but the standard
library. What only its host can do, it returns as a `Request`.
"""

from __future__ import annotations

from .editor import Editor, Mode, Request
from .keys import parse_keys
from .selection import Direction, Range, Selection

__all__ = [
    "Direction",
    "Editor",
    "Mode",
    "Range",
    "Request",
    "Selection",
    "parse_keys",
]
