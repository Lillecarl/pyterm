"""
The bindings on a real prompt_toolkit application: keys go through its
key processor, past its default emacs bindings, into the buffer.
"""

from __future__ import annotations

from prompt_toolkit.application import Application
from prompt_toolkit.application.current import set_app
from prompt_toolkit.buffer import Buffer
from prompt_toolkit.document import Document
from prompt_toolkit.filters import Condition, to_filter
from prompt_toolkit.key_binding.key_processor import KeyPress, _Flush
from prompt_toolkit.keys import Keys
from prompt_toolkit.layout import Layout, Window
from prompt_toolkit.layout.controls import BufferControl
from prompt_toolkit.output import DummyOutput

from ptkhx import Mode
from ptkhx.bindings import HelixBindings
from ptkhx.keys import parse_keys

_PRESSES = {
    "<esc>": KeyPress(Keys.Escape, "\x1b"),
    "<ret>": KeyPress(Keys.ControlM, "\r"),
    "<tab>": KeyPress(Keys.ControlI, "\t"),
    "<backspace>": KeyPress(Keys.Backspace, "\x7f"),
    "<left>": KeyPress(Keys.Left, ""),
    "<right>": KeyPress(Keys.Right, ""),
}


class Typist:
    "One buffer in an application with prompt_toolkit's own bindings, and Helix's last."

    def __init__(self, text: str = "", helix: HelixBindings | None = None, multiline: bool = True) -> None:
        self.accepted: list[str] = []
        self.buffer = Buffer(
            document=Document(text, 0),
            multiline=multiline,
            accept_handler=lambda buffer: bool(self.accepted.append(buffer.text)),
        )
        self.helix = helix or HelixBindings()
        self.app = Application(
            layout=Layout(Window(BufferControl(self.buffer, input_processors=[self.helix.processor()]))),
            key_bindings=self.helix.key_bindings,
            output=DummyOutput(),
        )
        # No timer: a lone Escape is flushed by hand, as the timeout would.
        self.app.timeoutlen = None

    def type(self, keys: str) -> None:
        processor = self.app.key_processor
        with set_app(self.app):
            for token in parse_keys(keys):
                if token.startswith("<A-"):
                    processor.feed_multiple([_PRESSES["<esc>"], KeyPress(token[3:-1], token[3:-1])])
                else:
                    processor.feed(_PRESSES.get(token) or KeyPress(token, token))
                processor.process_keys()
                processor.feed(_Flush)
                processor.process_keys()

    @property
    def mode(self) -> Mode:
        return self.helix.mode_of(self.buffer)


def test_typing_is_prompt_toolkit_s_in_insert_mode():
    typist = Typist()
    typist.type("hello")
    assert typist.buffer.text == "hello"
    assert typist.mode is Mode.INSERT


def test_escape_then_b_goes_back_a_word():
    "Not emacs's backward-word, which owns `escape b` by name."
    typist = Typist()
    typist.type("hello world<esc>b")
    assert typist.mode is Mode.NORMAL
    assert typist.helix.selection_spans(typist.buffer) == [(6, 11)]


def test_normal_mode_edits_the_buffer():
    typist = Typist()
    typist.type("hello world<esc>bd")
    assert typist.buffer.text == "hello "


def test_several_cursors_type_together():
    typist = Typist()
    typist.type("a b a<esc>%sa<ret>cx<esc>")
    assert typist.buffer.text == "x b x"


def test_enter_accepts_in_normal_mode():
    typist = Typist("ls", multiline=False)
    typist.type("<esc><ret>")
    assert typist.accepted == ["ls"]


def test_reset_starts_a_line_in_insert_mode():
    typist = Typist()
    typist.type("abc<esc>")
    typist.buffer.reset()
    typist.helix.reset(typist.buffer)
    assert typist.mode is Mode.INSERT


def test_a_filter_hands_the_keys_back():
    "A host that turns Helix keys off gets prompt_toolkit's emacs keys."
    on = [True]
    typist = Typist(helix=HelixBindings(filter=Condition(lambda: on[0])))
    typist.type("ab<esc>")
    assert typist.mode is Mode.NORMAL
    on[0] = False
    typist.type("x")
    assert typist.buffer.text == "abx"


def a_reader(text: str) -> Typist:
    "A read-only buffer in normal mode, as pymux's copy mode is."
    typist = Typist(text, helix=HelixBindings(initial_mode=Mode.NORMAL, read_only=True))
    typist.buffer.read_only = to_filter(True)
    return typist


def test_a_read_only_editor_moves_and_selects():
    typist = a_reader("hello world")
    typist.type("ww")
    assert typist.helix.selection_spans(typist.buffer) == [(6, 11)]


def test_a_read_only_editor_refuses_every_edit():
    "Each would raise EditReadOnlyBuffer, had it reached the buffer."
    typist = a_reader("hello world")
    for keys in ("d", "cx", "ix", "ax", "o", "rx", "p", "J", ">", "~", "u", "<A-d>"):
        typist.type(keys)
        assert typist.buffer.text == "hello world", keys
        assert typist.mode is Mode.NORMAL, keys


def test_a_refused_edit_leaves_the_selection():
    typist = a_reader("hello world")
    typist.type("w")
    typist.type("d")
    assert typist.helix.selection_spans(typist.buffer) == [(0, 6)]


def test_search_reads_a_read_only_buffer():
    typist = a_reader("one two\nthree two")
    typist.type("/two<ret>n")
    assert typist.helix.selection_spans(typist.buffer) == [(14, 17)]


def test_a_cursor_the_host_moved_is_where_the_next_key_starts():
    "A click moves the buffer's cursor and nothing of the editor's."
    typist = a_reader("one two three")
    typist.type("w")
    typist.buffer.cursor_position = 8
    typist.type("e")
    assert typist.helix.selection_spans(typist.buffer) == [(8, 13)]


def test_each_buffer_has_its_own_editor():
    helix = HelixBindings()
    one, two = Typist(helix=helix), Typist(helix=helix)
    one.type("a<esc>")
    assert one.mode is Mode.NORMAL
    assert two.mode is Mode.INSERT
