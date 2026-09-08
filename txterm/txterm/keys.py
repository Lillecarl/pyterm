"""
What a key of Textual sends to the program.

Textual reads the escape sequences of the terminal of the user and hands
a widget a name: "up", "ctrl+c", "f5". A program in a pane wants the
sequence back, and in the encoding that *this* pane asked for, which is
not always the one the outer terminal sent.

So this file only undoes the naming. It turns a name back into the plain
vt100 sequence, and `Screen.encode_key` does the rest: the cursor
keys of application mode, and the kitty keyboard protocol when the
program turned it on. ptterm has the same pair, against
prompt_toolkit's table.

**The table is Textual's own, read backwards.** Writing the sequences
out again here would be a second table to keep in step with the first,
and the two would disagree the day Textual learns a key.
Lillecarl/pymux#119 is that same disagreement, between the two tables
that already exist.
"""

from typing import Dict

from textual import events
from textual._ansi_sequences import ANSI_SEQUENCES_KEYS

__all__ = ("KEY_DATA", "data_of")


def _keys_to_data() -> Dict[str, str]:
    """
    The sequence that each key of Textual arrives as.

    Only a sequence that names one key is of use: a sequence that names
    several is one press that Textual splits, and there is no single
    key to put back.

    **The first sequence wins.** A key has more than one spelling, and
    the table lists the plain one first: "ctrl+m" is "\\r" and also
    "\\x1b[27;5;13~", and a program that reads a line wants the first.
    """
    data: Dict[str, str] = {}
    for sequence, keys in ANSI_SEQUENCES_KEYS.items():
        if not isinstance(keys, tuple) or len(keys) != 1:
            continue
        data.setdefault(keys[0].value, sequence)
    return data


#: Where the first spelling of the table is not the one a program
#: expects, and what to send instead.
#:
#: One so far. Textual lists "\x08" for the backspace, which is what
#: ctrl+h sends. A terminal sends delete: `stty` on a fresh pty reports
#: "erase = ^?", so a pane that sent "\x08" would be a pane where the
#: backspace key does not erase in bash, in python, or anywhere else
#: that reads a line.
#:
#: **This loses ctrl+h**, and there is nothing here that can keep it:
#: Textual gives that key and the backspace key the same name, so what
#: reaches this file is one key and not two. Lillecarl/pymux#123.
CORRECTIONS = {
    "backspace": "\x7f",
}

#: The vt100 sequence for each key that Textual names.
KEY_DATA = {**_keys_to_data(), **CORRECTIONS}


def data_of(event: events.Key) -> str:
    """
    What one key press sends, before the pane encodes it.

    A printable key sends the character itself. Textual hands one over
    as it stands, so a letter, a digit and an emoji all take this route
    and no table has to hold them.

    A key with a name is looked up. An alias is tried after the name,
    because Textual reports a key under more than one of them: "enter"
    and "ctrl+m" are one press, and only one of the two is in the table.

    An empty string means that nothing here knows the key. The caller
    sends nothing, which is what a terminal does with a key it has no
    sequence for.
    """
    if event.is_printable and event.character:
        return event.character
    for name in event.aliases:
        data = KEY_DATA.get(name)
        if data is not None:
            return data
    return ""
