"""
Random key sequences, in real Helix and in ptkhx, and the two answers
compared. Lillecarl/pymux#749.

`cases.py` holds what somebody thought to ask. This asks what nobody
did: Hypothesis draws a short document and a few commands, `helix.run`
plays them in `hx` on a pty, and ptkhx plays them in Python. What each
draws -- the text, the mode, every range and its cursor -- must be the
same. A failure shrinks to the shortest sequence that still disagrees,
and that sequence belongs in `cases.py` once Helix's answer is known.

Only keys ptkhx implements are drawn: a key it lacks disagrees for a
reason nobody needs to be told. Never `:`, `q`, or the space menu,
which leave the document or open a picker.

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
from hypothesis import HealthCheck, given, seed, settings
from hypothesis import strategies as st

from ptkhx.testing import editor_from

EXAMPLES = int(os.environ.get("PTKHX_HUNT", "100"))
SEED = os.environ.get("PTKHX_HUNT_SEED", "")

#: The characters a document is made of: words, a space, brackets and
#: line breaks are what the motions and textobjects tell apart.
ALPHABET = "ab (x).\n"

#: What a typed character, a find or a replace takes.
CHARACTERS = "ab (x)."

#: Commands of one key, or one fixed sequence.
PLAIN = (
    *"hjklwWeEbBxX;v_,C%)(nNuUyPpR~`J>d",
    "<lt>",
    "<esc>",
    *("<A-%s>" % key for key in ";:.Cs_-,`dJ"),
    "gg",
    "ge",
    "gh",
    "gl",
    "gs",
    "mm",
)

#: Commands that enter insert mode, before what is typed there.
INSERTS = (*"iaIAoOc", "<A-c>")

#: Commands that read a regex up to Enter.
REGEXES = (*"sSK/?", "<A-K>")

#: The keys a textobject or a surround names.
PAIRS = "([w"


def _token(char: str) -> str:
    "One character as a key token: `<` alone would open a name."
    return "<lt>" if char == "<" else char


characters = st.sampled_from(CHARACTERS).map(_token)

typed = st.lists(
    st.one_of(characters, st.sampled_from(["<ret>", "<backspace>"])),
    max_size=4,
).map("".join)

commands = st.one_of(
    st.sampled_from(PLAIN),
    st.tuples(st.sampled_from(["", "2", "3"]), st.sampled_from(PLAIN)).map("".join),
    st.tuples(st.sampled_from(INSERTS), typed).map(lambda pair: pair[0] + pair[1] + "<esc>"),
    st.tuples(st.sampled_from("ftFTr"), characters).map("".join),
    st.tuples(st.sampled_from(["mi", "ma", "ms", "md"]), st.sampled_from(PAIRS)).map("".join),
    st.tuples(st.sampled_from(REGEXES), st.text(alphabet="ab.^x", min_size=1, max_size=3)).map(
        lambda pair: pair[0] + pair[1] + "<ret>"
    ),
)

documents = st.text(alphabet=ALPHABET, min_size=1, max_size=24)


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
@given(text=documents, keys=st.lists(commands, min_size=1, max_size=5).map("".join))
async def test_ptkhx_draws_what_helix_draws(text: str, keys: str):
    start = _start(text)
    editor = editor_from(start)
    editor.feed_keys(keys)
    ours = annotate(seen(editor.text, editor.selection, editor.mode))

    with tempfile.TemporaryDirectory() as home:
        theirs = annotate(await run(start, keys, Path(home)))

    assert ours == theirs, "keys %r on %r" % (keys, start)
