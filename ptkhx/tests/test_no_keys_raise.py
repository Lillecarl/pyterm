"""
No key sequence makes ptkhx raise.

The hunt against Helix (`hunt_against_helix.py`) found an `IndexError`
in `md[` with the cursor past the end of a line. That needs no Helix to
find, so this draws the same commands against ptkhx alone, a thousand
at a time, on shell lines: no trailing line break, and a cursor that
may stand past the last character.
"""

from __future__ import annotations

from hypothesis import given, settings
from hypothesis import strategies as st
from keystrokes import ALPHABET, keys

from ptkhx import Editor, Selection
from ptkhx.keys import parse_keys


@settings(max_examples=1000, deadline=None, derandomize=True, database=None)
@given(text=st.text(alphabet=ALPHABET, max_size=24), keys=keys, at_the_end=st.booleans())
def test_no_key_sequence_raises(text: str, keys: str, at_the_end: bool):
    editor = Editor(text=text, selection=Selection.point(len(text) if at_the_end else 0))
    editor.ensure_invariants()
    for key in parse_keys(keys):
        editor.feed(key)
