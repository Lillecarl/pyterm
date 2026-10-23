"""
Random key sequences, in real Helix and in ptkhx, and the two answers
compared. Lillecarl/pymux#749.

`cases.py` holds what somebody thought to ask. This asks what nobody
did: Hypothesis draws a short document and a few commands from
`keystrokes.py`, `helix.run` plays them in `hx` on a pty, and ptkhx
plays them in Python. What each draws -- the text, the mode, every
range and its cursor -- must be the same. A failure shrinks to the
shortest sequence that still disagrees, and that sequence belongs in
`cases.py` once Helix's answer is known.

**A document ends in a line break**, as a file does. Helix keeps one
there for a cursor to stand on, and appends one at the end of a file
without it; a shell line has none, and ptkhx lets the cursor stand past
the end instead. That difference is deliberate (`editor.py` says so),
so the hunt leaves it out. An edit can still take the line break away,
and an `a` there is skipped as it is met.

`PTKHX_HUNT` says how many examples to try. Each one starts Helix, so
an example costs a second or two. `PTKHX_HUNT_SEED` draws a different
set, so several hunts can run at once; without it the set is the same
every run.
"""

from __future__ import annotations

import os
import tempfile
from pathlib import Path

from helix import annotate, run, seen
from hypothesis import HealthCheck, assume, given, seed, settings
from hypothesis import strategies as st
from keystrokes import ALPHABET, keys

from ptkhx import Editor, Mode
from ptkhx.keys import parse_keys
from ptkhx.testing import editor_from

EXAMPLES = int(os.environ.get("PTKHX_HUNT", "100"))
SEED = os.environ.get("PTKHX_HUNT_SEED", "")

documents = st.text(alphabet=ALPHABET, max_size=24).map(lambda text: text + "\n")


def _appends_to_a_shell_line(editor: Editor, token: str) -> bool:
    """
    Is this `a` the documented difference? Its last range reaches the end
    of a document that an edit left without a final line break, where
    Helix adds one and ptkhx, for a shell line, does not.
    """
    if token != "a" or editor.mode is Mode.INSERT or editor.reading or editor._pending:
        return False
    last = editor.selection[len(editor.selection) - 1]
    return not last.is_empty and last.end == len(editor.text) and not editor.text.endswith("\n")


def _start(text: str) -> str:
    "The document as Helix opens it: one cursor on the first character."
    return "#[%s|]#%s" % (text[0], text[1:])


@settings(
    max_examples=EXAMPLES,
    deadline=None,
    derandomize=not SEED,
    database=None,
    suppress_health_check=[HealthCheck.too_slow],
)
@seed(int(SEED or 0))
@given(text=documents, keys=keys)
async def test_ptkhx_draws_what_helix_draws(text: str, keys: str):
    start = _start(text)
    editor = editor_from(start)
    for token in parse_keys(keys):
        assume(not _appends_to_a_shell_line(editor, token))
        editor.feed(token)
    ours = annotate(seen(editor.text, editor.selection, editor.mode))

    with tempfile.TemporaryDirectory() as home:
        theirs = annotate(await run(start, keys, Path(home)))

    assert ours == theirs, "keys %r on %r" % (keys, start)
