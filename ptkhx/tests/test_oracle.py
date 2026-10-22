"""
The keymap on real Helix: each case of `cases.py`, run in `hx` on a pty
and read back off the screen. It says whether a case's answer is
Helix's, so `test_keymap.py` judges ptkhx against Helix and not against
a guess.
"""

from __future__ import annotations

import pytest
from cases import CASES, Case
from helix import annotate, run, seen

from ptkhx.testing import parse_annotated

pytestmark = pytest.mark.oracle


@pytest.mark.parametrize("case", CASES, ids=str)
async def test_helix_does_what_the_case_says(case: Case, tmp_path):
    got = await run(case.before, case.keys, tmp_path)
    text, selection = parse_annotated(case.after)
    assert annotate(got) == annotate(seen(text, selection, case.mode))
