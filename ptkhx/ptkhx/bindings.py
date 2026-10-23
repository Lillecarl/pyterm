"""
Helix editing on prompt_toolkit buffers: the key bindings, the painting
of selections and extra cursors, and the cursor shape.

Three jobs:

1. Turn prompt_toolkit key presses into the tokens `Editor.feed` reads.
2. Keep each buffer and its editor in step.
3. Turn a `Request` into what the host does: accept the line, complete,
   walk history.

**One editor per buffer.** A host may hold many buffers under one set
of bindings, as a pymux server holds a command line per client, so the
editors hang off the buffers and every binding finds its own through
`event.current_buffer`.

**Insert mode is prompt_toolkit's.** Typing, backspace, completion and
auto-suggestion already work there, and intercepting them would mean
doing them worse. Only Escape is bound in insert mode, and the editor
reads the buffer back on the way out. The exception is
`Editor.owns_input`: typing into several cursors, and typing a regex for
`s`. prompt_toolkit knows neither state, so while one is on every key
goes through the editor and the buffer is written from it.

A terminal has one cursor, and prompt_toolkit puts it at the buffer's
`cursor_position`, which is the primary's. `SelectionProcessor` paints
every other cursor, and every selection, into the fragments.

**Binding precedence.** prompt_toolkit sorts the bindings that match by
how many `Keys.Any` wildcards they hold and takes the last, so a binding
that names its key beats a wildcard whatever the order, and a tie goes
to the one added last. A host merges these bindings last, so they win
ties; a bare `Keys.Any` still loses to a default binding that names a
key, which is why the named keys are bound one by one.
"""

from __future__ import annotations

import weakref
from collections.abc import Callable
from typing import TYPE_CHECKING, Final

from prompt_toolkit.clipboard import ClipboardData
from prompt_toolkit.cursor_shapes import CursorShape, CursorShapeConfig
from prompt_toolkit.document import Document
from prompt_toolkit.filters import Condition, Filter, to_filter
from prompt_toolkit.key_binding import ConditionalKeyBindings, KeyBindings
from prompt_toolkit.keys import Keys
from prompt_toolkit.layout.processors import Processor, Transformation
from prompt_toolkit.layout.utils import explode_text_fragments

from .editor import Editor, Mode, Request
from .selection import Range, Selection

if TYPE_CHECKING:
    from prompt_toolkit.application import Application
    from prompt_toolkit.buffer import Buffer
    from prompt_toolkit.key_binding import KeyPressEvent
    from prompt_toolkit.layout.processors import TransformationInput

__all__ = [
    "FALLBACK_SELECTION_STYLE",
    "SECONDARY_CURSOR_STYLE",
    "TIMEOUTLEN",
    "CursorShapes",
    "HelixBindings",
    "SelectionProcessor",
]

#: prompt_toolkit's key -> the token `Editor.feed` reads. A key not here
#: is a printable character, used as it is, or one the editor ignores.
_NAMED: Final = {
    Keys.Escape: "<esc>",
    Keys.ControlM: "<ret>",
    Keys.ControlJ: "<ret>",
    Keys.ControlI: "<tab>",
    Keys.BackTab: "<tab>",
    Keys.Backspace: "<backspace>",
    Keys.Delete: "<del>",
    Keys.Left: "<left>",
    Keys.Right: "<right>",
    Keys.Up: "<up>",
    Keys.Down: "<down>",
    Keys.Home: "<home>",
    Keys.End: "<end>",
    Keys.PageUp: "<pageup>",
    Keys.PageDown: "<pagedown>",
}

#: The named keys bound one by one outside insert mode: the emacs
#: defaults name them, and a `Keys.Any` binding sorts behind those.
_NAMED_BINDINGS: Final = (
    Keys.Left,
    Keys.Right,
    Keys.Up,
    Keys.Down,
    Keys.Home,
    Keys.End,
    Keys.Backspace,
    Keys.Delete,
)

#: The Alt combinations Helix gives a meaning of its own.
#:
#: Each gives up "Escape, then that character within `TIMEOUTLEN`": the
#: two are the same bytes, and only the pause tells them apart. A person
#: takes longer than 50 ms between Escape and the next key. A paste or
#: a macro does not.
_ALT_KEYS: Final = frozenset(";:.dc`J" + ",sCK-_()")

#: Every printable character, each bound as `escape <char>`.
#:
#: A terminal sends Alt-x as ESC then x. The emacs defaults bind
#: `escape b` and `escape f` by name, which beats a wildcard, so without
#: claiming these, Escape and then `b` ran `backward-word` instead of
#: Helix's `b`. Named keys stay unclaimed: Alt-Backspace still deletes a
#: word.
_ESCAPE_FOLLOWERS: Final = tuple(chr(c) for c in range(0x20, 0x7F))

#: How long prompt_toolkit waits on an ambiguous prefix. A host sets its
#: application's `timeoutlen` to this.
#:
#: Claiming `escape <char>` makes a bare Escape the prefix of a longer
#: binding, so it waits for the next key or for this. At
#: prompt_toolkit's own 1 s, pressing Escape looks like nothing
#: happened. A real Alt-x arrives as two keys in one read and never
#: waits for it.
TIMEOUTLEN: Final = 0.05

#: Painted over a selection: a lifted background, for a dark terminal.
#: Reverse video is what a block cursor looks like, so a selection in it
#: would hide the cursor inside it.
FALLBACK_SELECTION_STYLE: Final = "bg:#3a3a4a"

#: Painted over every cursor but the primary: reverse video, which is
#: what the terminal's own block cursor looks like.
SECONDARY_CURSOR_STYLE: Final = "reverse"


def _accept(buffer: Buffer, _app: Application) -> None:
    buffer.validate_and_handle()


class HelixBindings:
    """
    Helix editing for every buffer these key bindings reach.

    :param accept: what Enter does with a buffer the editor accepts: a
        shell that reads a line continued in its own way plugs its parser
        in here.
    :param confirm_completion: whether Escape closes an open completion
        menu before it leaves insert mode.
    :param filter: gates every binding, for a host that switches Helix
        keys on and off.
    :param csi_u_enter: bind the CSI-u Enter of the kitty keyboard
        protocol, with Shift, Alt or Ctrl, as a new line.
    :param read_only: every editor refuses the keys that change its
        text, for a buffer a person only reads and selects in.
    """

    def __init__(
        self,
        *,
        initial_mode: Mode = Mode.INSERT,
        accept: Callable[[Buffer, Application], None] = _accept,
        confirm_completion: Callable[[], bool] = lambda: True,
        filter: Filter | bool = True,
        csi_u_enter: bool = False,
        read_only: bool = False,
    ) -> None:
        self.initial_mode = initial_mode
        self.read_only = read_only
        self.accept = accept
        self.confirm_completion = confirm_completion
        self.filter = to_filter(filter)
        #: prompt_toolkit removes no binding once a registry is merged, so
        #: a host that unloads turns them off here.
        self.enabled = True
        self.selection_style = FALLBACK_SELECTION_STYLE
        self.secondary_cursor_style = SECONDARY_CURSOR_STYLE
        self._editors: weakref.WeakKeyDictionary[Buffer, Editor] = weakref.WeakKeyDictionary()
        bound = KeyBindings()
        self._bind(bound, csi_u_enter)
        #: What a host merges last, so these win its ties.
        #:
        #: **One condition over the lot**, checked first: a key the host
        #: keeps pays for that check alone, and never for the current
        #: buffer and its editor. In pymux, every key for a pane went
        #: through a dozen of those lookups, 18% of a keystroke.
        self.key_bindings = ConditionalKeyBindings(bound, Condition(self._active))

    # ------------------------------------------------------------------
    # Editors.

    def editor_for(self, buffer: Buffer) -> Editor:
        "The editor of `buffer`, made in the initial mode on first use."
        editor = self._editors.get(buffer)
        if editor is None:
            editor = Editor(
                text=buffer.text,
                selection=Selection.point(buffer.cursor_position),
                read_only=self.read_only,
            )
            editor.mode = self.initial_mode
            editor.reset_transient()
            self._editors[buffer] = editor
        return editor

    def reset(self, buffer: Buffer) -> None:
        """
        Start a fresh line in `buffer`, in the initial mode. Undo
        history, a dangling `g` and a half-typed count all belong to the
        line before.
        """
        editor = self.editor_for(buffer)
        editor.mode = self.initial_mode
        editor.text = buffer.text
        editor.selection = Selection.point(buffer.cursor_position)
        editor.reset_transient()

    def mode_of(self, buffer: Buffer) -> Mode:
        return self.editor_for(buffer).mode

    def pending_of(self, buffer: Buffer) -> str:
        "The half-typed command for a status line: a count, a menu key, a regex."
        return self.editor_for(buffer).pending

    # ------------------------------------------------------------------
    # Keeping a buffer and its editor in step.

    def _sync_in(self, buffer: Buffer) -> Editor:
        "Take what the buffer says before a key: insert mode, history and completion change it."
        editor = self.editor_for(buffer)
        if editor.owns_input:
            # The buffer is written from the editor now. Reading its one
            # cursor back would fold every other cursor onto it.
            return editor
        if editor.mode is Mode.INSERT:
            # Through the edit, not over it: typing at the anchor carries
            # it along, or leaving insert would find the line selected.
            editor.adopt_text(buffer.text)
            editor.range = Range(editor.range.anchor, buffer.cursor_position)
        else:
            # Outside insert mode a new text means something replaced the
            # buffer whole, and there is no edit to carry a selection through.
            # A cursor the host moved, with a click or its own search, starts
            # a fresh range there.
            if buffer.text != editor.text or buffer.cursor_position != editor.caret:
                editor.range = Range.point(buffer.cursor_position)
            editor.text = buffer.text
        editor.ensure_invariants()
        return editor

    @staticmethod
    def _sync_out(buffer: Buffer, editor: Editor) -> None:
        if buffer.text != editor.text:
            # One assignment: text then cursor shows `on_text_changed` a
            # cursor past the end of the new text.
            buffer.document = Document(editor.text, editor.caret)
        elif buffer.cursor_position != editor.caret:
            buffer.cursor_position = editor.caret

    def insert_text(self, buffer: Buffer, text: str) -> None:
        "Type `text` at every cursor of `buffer`'s editor, and show it."
        editor = self.editor_for(buffer)
        editor.insert_text(text)
        self._sync_out(buffer, editor)

    def adopt(self, buffer: Buffer) -> None:
        "Read the buffer again, after something replaced it whole."
        editor = self.editor_for(buffer)
        editor.text = buffer.text
        editor.range = Range.point(buffer.cursor_position)
        editor.ensure_invariants()
        self._sync_out(buffer, editor)

    # ------------------------------------------------------------------
    # What the painting reads.

    def selection_spans(self, buffer: Buffer) -> list[tuple[int, int]]:
        """
        The spans to paint as selected. Not prompt_toolkit's
        `selection_state`: its selection leaves out the character under
        the cursor, a live one switches off `emacs_insert_mode`, which
        hosts gate Enter on, and there is only one of it.

        A one-wide range is left out: the block cursor shows it.
        """
        editor = self.editor_for(buffer)
        if editor.mode is Mode.INSERT:
            return []
        return [(rng.start, rng.end) for rng in editor.selection if len(rng) > 1]

    def secondary_cursors(self, buffer: Buffer) -> list[int]:
        "Every cursor but the primary, which the terminal draws."
        editor = self.editor_for(buffer)
        selection = editor.selection
        if not selection.multi:
            return []
        return [editor.caret_of(rng) for index, rng in enumerate(selection) if index != selection.primary_index]

    def processor(self) -> SelectionProcessor:
        "The processor a host adds to the controls of its buffers."
        return SelectionProcessor(self)

    def cursor_shapes(self) -> CursorShapes:
        return CursorShapes(self)

    # ------------------------------------------------------------------
    # Bindings.

    def _active(self) -> bool:
        return self.enabled and self.filter()

    def _ours(self) -> bool:
        "Does this key go to the editor, and not to the buffer? Asked only while `_active`."
        editor = self.editor_for(_current_buffer())
        return editor.mode is not Mode.INSERT or editor.owns_input

    def before_escape(self, event: KeyPressEvent) -> bool:
        "A host's use of Escape before the editor's. True when it took it."
        return self._cancel_completion(event)

    def _bind(self, bound: KeyBindings, csi_u_enter: bool) -> None:
        # Every filter here is asked only while `_active` says yes.
        add = bound.add
        ours = Condition(self._ours)
        reading = Condition(lambda: self.editor_for(_current_buffer()).reading)

        @add(Keys.Any, filter=ours)
        def _any(event: KeyPressEvent) -> None:
            self._dispatch(event, event.key_sequence[0].data or "")

        # Each printable character again, by name: `Keys.Any` loses to a
        # binding that names its key, and a host may bind one in insert
        # mode, as xonsh's abbreviations bind space. Typing into several
        # cursors has to reach all of them.
        for char in _ESCAPE_FOLLOWERS:

            @add(char, filter=ours)
            def _printable(event: KeyPressEvent, _char: str = char) -> None:
                self._dispatch(event, _char)

        for key in _NAMED_BINDINGS:

            @add(key, filter=ours)
            def _named(event: KeyPressEvent) -> None:
                self._dispatch(event, _NAMED.get(event.key_sequence[0].key, ""))

        # Enter, while a regex is read: it means "that is the pattern".
        # Everywhere else it stays the host's.
        for key in (Keys.ControlM, Keys.ControlJ):

            @add(key, filter=reading)
            def _reading_enter(event: KeyPressEvent) -> None:
                self._dispatch(event, "<ret>")

        # Escape in every mode: it is how insert mode is left.
        @add(Keys.Escape)
        def _escape(event: KeyPressEvent) -> None:
            if self.before_escape(event):
                return
            self._dispatch(event, "<esc>")

        if csi_u_enter:
            inserting = Condition(
                lambda: (
                    not self.editor_for(_current_buffer()).owns_input and self.mode_of(_current_buffer()) is Mode.INSERT
                )
            )
            normal = Condition(lambda: self.mode_of(_current_buffer()) is Mode.NORMAL)
            for modifier in ("2", "3", "5"):  # shift, alt, ctrl

                @add(Keys.Escape, "[", "1", "3", ";", modifier, "u", filter=inserting)
                def _csi_u_enter(event: KeyPressEvent) -> None:
                    event.current_buffer.insert_text("\n")

                @add(Keys.Escape, "[", "1", "3", ";", modifier, "u", filter=normal)
                def _csi_u_enter_normal(event: KeyPressEvent) -> None:
                    buffer = event.current_buffer
                    buffer.insert_text("\n")
                    self.adopt(buffer)
                    self.editor_for(buffer).mode = Mode.INSERT

        for char in _ESCAPE_FOLLOWERS:

            @add(Keys.Escape, char)
            def _escape_then(event: KeyPressEvent, _char: str = char) -> None:
                insert = self.mode_of(event.current_buffer) is Mode.INSERT
                if not insert and _char in _ALT_KEYS:
                    self._dispatch(event, f"<A-{_char}>")
                elif self.before_escape(event):
                    # The Escape went on the host's own use, so the mode
                    # stands and the character is ordinary input in it.
                    if insert:
                        event.current_buffer.insert_text(_char)
                    else:
                        self._dispatch(event, _char)
                else:
                    # Escape first, so the character is read in the mode
                    # Escape leaves: typing, Escape, `b` goes back a word.
                    self._dispatch(event, "<esc>")
                    self._dispatch(event, _char)

    def _cancel_completion(self, event: KeyPressEvent) -> bool:
        """
        Escape closes an open completion menu first, as it does
        everywhere else, and leaves insert mode on the next press.
        """
        buffer = event.current_buffer
        if buffer.complete_state is None or not self.confirm_completion():
            return False
        buffer.cancel_completion()
        return True

    def _dispatch(self, event: KeyPressEvent, token: str) -> None:
        if not token:
            return
        buffer = event.current_buffer
        editor = self._sync_in(buffer)
        self._wire_clipboard(editor, event.app)
        request = editor.feed(token)
        self._sync_out(buffer, editor)
        if request is not None:
            self._handle(request, event)

    @staticmethod
    def _wire_clipboard(editor: Editor, app: Application) -> None:
        def get() -> str:
            data = app.clipboard.get_data()
            return data.text if data is not None else ""

        editor.clipboard_get = get
        editor.clipboard_set = lambda text: app.clipboard.set_data(ClipboardData(text))

    def _handle(self, request: Request, event: KeyPressEvent) -> None:
        buffer = event.current_buffer
        if request is Request.ACCEPT:
            self.accept(buffer, event.app)
        elif request is Request.ABORT:
            buffer.reset()
        elif request is Request.COMPLETE:
            buffer.start_completion()
        elif request is Request.HISTORY_PREV:
            buffer.history_backward(count=event.arg)
            self.adopt(buffer)
        elif request is Request.HISTORY_NEXT:
            buffer.history_forward(count=event.arg)
            self.adopt(buffer)


def _current_buffer() -> Buffer:
    from prompt_toolkit.application.current import get_app

    return get_app().current_buffer


class SelectionProcessor(Processor):
    """
    Paint the selections, and every cursor the terminal cannot draw.

    prompt_toolkit's `HighlightSelectionProcessor`, with the spans taken
    from the editor and an explicit style in place of `class:selected`,
    which is reverse video and so looks like the cursor inside it. The
    other cursors are painted afterwards, in reverse video, and look the
    same as the primary inside its own selection.
    """

    def __init__(self, helix: HelixBindings) -> None:
        self.helix = helix

    def apply_transformation(self, transformation_input: TransformationInput) -> Transformation:
        control, document, lineno, source_to_display, fragments, *_ = transformation_input.unpack()
        buffer = control.buffer
        spans = self.helix.selection_spans(buffer)
        cursors = self.helix.secondary_cursors(buffer)
        if not spans and not cursors:
            return Transformation(fragments)

        row_start = document.translate_row_col_to_index(lineno, 0)
        row_end = row_start + len(document.lines[lineno])
        # Exploded only when this row has something to paint.
        exploded: list | None = None

        def paint(begin: int, end: int, style: str) -> None:
            nonlocal exploded
            begin, end = max(row_start, begin), min(row_end, end)
            if begin >= end:
                return
            if exploded is None:
                exploded = explode_text_fragments(fragments)
            for i in range(source_to_display(begin - row_start), source_to_display(end - row_start)):
                if i < len(exploded):
                    existing, text, *rest = exploded[i]
                    exploded[i] = (existing + style, text, *rest)

        for start, end in spans:
            paint(start, end, f" {self.helix.selection_style} ")
        for position in cursors:
            paint(position, position + 1, f" {self.helix.secondary_cursor_style} ")
        return Transformation(fragments if exploded is None else exploded)


class CursorShapes(CursorShapeConfig):
    "A block in normal mode, a bar in insert, an underline in select."

    _SHAPES: Final = {
        Mode.NORMAL: CursorShape.BLOCK,
        Mode.INSERT: CursorShape.BEAM,
        Mode.SELECT: CursorShape.UNDERLINE,
    }

    def __init__(self, helix: HelixBindings) -> None:
        self.helix = helix

    def get_cursor_shape(self, application: Application) -> CursorShape:
        return self._SHAPES[self.helix.mode_of(application.current_buffer)]
