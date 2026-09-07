"""
What a key of Textual sends, before the pane encodes it.

The table is Textual's own, read backwards, so these tests are about the
reading and not about the sequences. A version of Textual that renames a
key or moves the table fails here, loudly, instead of leaving a terminal
that quietly drops the arrow keys.
"""
import pytest
from textual import events
from txterm.keys import KEY_DATA, data_of


def press(key: str, character=None) -> events.Key:
    return events.Key(key, character)


@pytest.mark.parametrize(
    "key,data",
    [
        ("up", "\x1b[A"),
        ("down", "\x1b[B"),
        ("right", "\x1b[C"),
        ("left", "\x1b[D"),
        ("home", "\x1b[1~"),
        ("escape", "\x1b"),
        ("backspace", "\x7f"),
        ("tab", "\t"),
        ("enter", "\r"),
        ("ctrl+c", "\x03"),
        ("ctrl+d", "\x04"),
    ],
)
def test_a_key_with_a_name_sends_its_sequence(key, data):
    assert data_of(press(key)) == data


def test_the_plain_spelling_of_a_key_wins():
    """
    A key has more than one spelling, and a program that reads a line
    wants the plain one: "\\r" and not "CSI 27 ; 5 ; 13 ~".
    """
    assert KEY_DATA["enter"] == "\r"


@pytest.mark.parametrize("character", ["a", "Z", "7", "@", "ä", "日", "🙂"])
def test_a_printable_key_sends_itself(character):
    "No table holds the letters. Textual hands the character over."
    assert data_of(press(character, character)) == character


def test_the_space_bar_sends_a_space():
    "It has a name and it is printable. Either route gives the same."
    assert data_of(press("space", " ")) == " "


def test_the_backspace_erases():
    """
    Textual lists "\\x08" for the backspace, which is what ctrl+h sends.
    A terminal sends delete, and a pty says so: `stty` reports
    "erase = ^?". A pane that sent the other one would be a pane where
    the backspace key does not erase.

    Textual gives ctrl+h and the backspace key the same name, so a pane
    cannot tell the two apart and one of them has to win. The backspace
    is the one a person presses. Lillecarl/pymux#123.
    """
    assert data_of(press("backspace")) == "\x7f"


def test_a_key_that_nothing_knows_sends_nothing():
    """
    A terminal has no sequence for every key a keyboard has. Sending
    nothing is what one does with such a key.
    """
    assert data_of(press("hyper+nonsense")) == ""


def test_the_table_is_not_empty():
    """
    The guard on the reading. An empty table would pass every test that
    asks what a key sends by looking it up in the same place.
    """
    assert len(KEY_DATA) > 50
