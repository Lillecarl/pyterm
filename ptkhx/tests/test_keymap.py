"""
The keymap on ptkhx: each case of `cases.py`, judged by what Helix draws.
"""

from __future__ import annotations

import pytest
from cases import CASES, Case
from helix import annotate, seen

from ptkhx.testing import editor_from, parse_annotated


@pytest.mark.parametrize("case", CASES, ids=str)
def test_ptkhx_does_what_helix_does(case: Case):
    editor = editor_from(case.before)
    editor.feed_keys(case.keys)
    got = seen(editor.text, editor.selection, editor.mode)
    text, selection = parse_annotated(case.after)
    assert annotate(got) == annotate(seen(text, selection, case.mode))
