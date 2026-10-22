"""
Hypothesis strategies for documents and Helix commands.

Only keys ptkhx implements are drawn: a key it lacks disagrees with
Helix for a reason nobody needs to be told. Never `:`, `q`, or the space
menu, which leave the document or open a picker.
"""

from __future__ import annotations

from hypothesis import strategies as st

__all__ = ["ALPHABET", "commands", "keys"]

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

#: A few commands, as one key sequence.
keys = st.lists(commands, min_size=1, max_size=5).map("".join)
