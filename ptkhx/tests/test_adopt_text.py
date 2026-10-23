"""
`Editor.adopt_text` finds what changed a block at a time. It must find
what a loop over every character finds, across the block's edges too.
"""

from __future__ import annotations

from hypothesis import given, settings
from hypothesis import strategies as st

from ptkhx.editor import _BLOCK, _common_prefix, _common_suffix

#: Long enough to cross a block, from few characters so the two agree long.
texts = st.text(alphabet="ab", max_size=3 * _BLOCK)


def _prefix(one: str, other: str) -> int:
    at = 0
    while at < min(len(one), len(other)) and one[at] == other[at]:
        at += 1
    return at


@settings(max_examples=300, deadline=None, derandomize=True, database=None)
@given(texts, st.integers(0, 3 * _BLOCK), st.text(alphabet="ab", max_size=3))
def test_the_block_scan_finds_what_a_character_scan_finds(text: str, at: int, inserted: str):
    at = min(at, len(text))
    edited = text[:at] + inserted + text[at:]
    prefix = _common_prefix(text, edited)
    assert prefix == _prefix(text, edited)
    limit = min(len(text), len(edited)) - prefix
    assert _common_suffix(text, edited, limit) == min(limit, _prefix(text[::-1], edited[::-1]))
