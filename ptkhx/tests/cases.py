"""
The keymap cases, in Helix's own notation. Each is a start, the keys,
and what Helix leaves. `test_keymap.py` runs them on ptkhx, and
`test_oracle.py` runs them on real Helix.

A start holds one range: the oracle puts it on Helix with keys, and
keys reach one range. More cursors come from the keys themselves.
"""

from __future__ import annotations

from dataclasses import dataclass

from ptkhx import Mode

__all__ = ["CASES", "Case"]


@dataclass(frozen=True)
class Case:
    name: str
    before: str
    keys: str
    after: str
    mode: Mode = Mode.NORMAL

    def __str__(self) -> str:
        return self.name


CASES = [
    # Motions.
    Case("l", "#[h|]#ello", "l", "h#[e|]#llo"),
    Case("h", "he#[l|]#lo", "h", "h#[e|]#llo"),
    Case("w", "#[h|]#ello world", "w", "#[hello |]#world"),
    Case("2w", "#[h|]#ello world again", "2w", "hello #[world |]#again"),
    Case("e", "#[h|]#ello world", "e", "#[hello|]# world"),
    Case("b", "hello #[w|]#orld", "b", "#[|hello ]#world"),
    Case("W", "#[a|]#.b c", "W", "#[a.b |]#c"),
    Case("j", "#[a|]#bc\ndef", "j", "abc\n#[d|]#ef"),
    Case("k", "abc\nd#[e|]#f", "k", "a#[b|]#c\ndef"),
    Case("j keeps the column", "ab#[c|]#d\nx\nabcd", "jj", "abcd\nx\nab#[c|]#d"),
    Case("f", "#[a|]#bc def", "fd", "#[abc d|]#ef"),
    Case("t", "#[a|]#bc def", "td", "#[abc |]#def"),
    Case("F", "abc d#[e|]#f", "Fa", "#[|abc de]#f"),
    Case("gh", "ab#[c|]#d", "gh", "#[a|]#bcd"),
    Case("gl", "#[a|]#bcd", "gl", "abc#[d|]#"),
    Case("ge", "#[a|]#bc\ndef", "ge", "abc\n#[d|]#ef"),
    # Both land on the first column, blank or not.
    Case("ge-indented", "ab#[c|]#\n  def", "ge", "abc\n#[ |]# def"),
    Case("gg", "abc\nd#[e|]#f", "gg", "#[a|]#bc\ndef"),
    # Not onto the empty line after the last line break.
    Case("ge-final-line-break", "#[a|]#\nb\n", "ge", "a\n#[b|]#\n"),
    Case("3gg-final-line-break", "#[a|]#\nb\n", "3gg", "a\n#[b|]#\n"),
    Case("gg-indented", "  abc\nd#[e|]#f", "gg", "#[ |]# abc\ndef"),
    Case("mm", "#[(|]#a b)", "mm", "(a b#[)|]#"),
    # A document with no syntax: off a bracket, `mm` stays.
    Case("mm-off-a-bracket", "#[a|]#()", "mm", "#[a|]#()"),
    Case("mm-select", "#[(|]#a)", "vmm", "#[(a)|]#", Mode.SELECT),
    # Selections.
    Case("x", "#[a|]#bc\ndef", "x", "#[abc\n|]#def"),
    Case("xx", "#[a|]#bc\ndef\nghi", "xx", "#[abc\ndef\n|]#ghi"),
    Case("%", "a#[b|]#c\ndef", "%", "#[abc\ndef|]#"),
    Case("v and l", "#[a|]#bcd", "vll", "#[abc|]#d", Mode.SELECT),
    Case(";", "#[abc|]#d", ";", "ab#[c|]#d"),
    Case("A-;", "#[abc|]#d", "<A-;>", "#[|abc]#d"),
    Case("miw", "ab#[c|]# def", "miw", "#[abc|]# def"),
    Case("mi(", "(a#[b|]#c)", "mi(", "(#[abc|]#)"),
    Case("ma(", "(a#[b|]#c)", "ma(", "#[(abc)|]#"),
    # Several cursors.
    Case("C", "#[a|]#bc\ndef", "C", "#(a|)#bc\n#[d|]#ef"),
    # The first match is the primary.
    Case("s", "#[a b a|]#", "sa<ret>", "#[a|]# b #(a|)#"),
    Case("S", "#[a,b|]#", "S,<ret>", "#[a|]#,#(b|)#"),
    Case(",", "#[a b a|]#", "sa<ret>,", "#[a|]# b a"),
    # A regex ignores case unless it holds a capital, and `^` is every line.
    Case("s-smart-case", "#[aA|]#", "sa<ret>", "#[a|]##(A|)#"),
    Case("s-capital", "#[aA|]#", "sA<ret>", "a#[A|]#"),
    Case("s-multiline", "#[ab\nab|]#", "s^a<ret>", "#[a|]#b\n#(a|)#b"),
    # An empty match is a cursor, unless it sits just past the selection.
    Case("s-empty-match", "#[aa|]#\nb", "s^<ret>", "#[a|]#a\nb"),
    Case("s-empty-matches", "#[a\nb|]#", "s^<ret>", "#[a|]#\n#(b|)#"),
    # Search starts after the primary and wraps.
    Case("/", "#[a|]#bc abc", "/b<ret>", "a#[b|]#c abc"),
    Case("/-several", "#[a|]#bc abc", "/bc<ret>", "a#[bc|]# abc"),
    Case("/-wraps", "abc a#[b|]#c", "/b<ret>", "a#[b|]#c abc"),
    Case("/-esc", "#[a|]#bc", "/b<esc>", "#[a|]#bc"),
    Case("/-smart-case", "ab#[c|]# ABC", "/b<ret>", "abc A#[B|]#C"),
    Case("/-capital", "#[a|]#Bc abc", "/B<ret>", "a#[B|]#c abc"),
    Case("?", "abc a#[b|]#c", "?b<ret>", "a#[b|]#c abc"),
    Case("?-wraps", "a#[b|]#c abc", "?b<ret>", "abc a#[b|]#c"),
    Case("n", "#[a|]#xa xa", "/x<ret>n", "axa #[x|]#a"),
    Case("N", "#[a|]#x ax ax", "/x<ret>nN", "a#[x|]# ax ax"),
    Case("2n", "#[a|]#x ax ax", "/x<ret>2n", "ax ax a#[x|]#"),
    Case("/-select", "#[a|]#xax", "v/x<ret>", "#(a|)##[x|]#ax", Mode.SELECT),
    Case("/-line", "#[a|]#bc\nabc", "/^a<ret>", "abc\n#[a|]#bc"),
    # Across lines.
    Case("gl-multiline", "#[a|]#bc\ndef", "gl", "ab#[c|]#\ndef"),
    Case("end-multiline", "#[a|]#bc\ndef", "<end>", "ab#[c|]#\ndef"),
    Case("x-last-line", "abc\n#[d|]#ef", "x", "abc\n#[def|]#"),
    # The selection keeps its length, so it ends inside the joined line.
    Case("J-multiline", "#[a|]#b\ncd\nef", "xJ", "#[ab |]#cd\nef"),
    # Changes.
    Case("d", "#[a|]#bc", "d", "#[b|]#c"),
    Case("wd", "#[h|]#ello world", "wd", "#[w|]#orld"),
    Case("c", "#[ab|]#c", "cx<esc>", "x#[c|]#"),
    # Whole lines change into one empty line where they stood.
    Case("c-whole-lines", "a\n#[b|]#\nc", "xc<esc>", "a\n#[\n|]#c"),
    Case("c-the-last-line-break", "#[\n|]#", "c<esc>", "#[\n|]#"),
    Case("i", "a#[b|]#c", "ix<esc>", "ax#[b|]#c"),
    # Appending extends the selection over what was typed.
    Case("a", "a#[b|]#c", "ax<esc>", "a#[bx|]#c"),
    Case("I", "  a#[b|]#c", "Ix<esc>", "  x#[a|]#bc"),
    # A line of blanks has no first character that is not one.
    Case("I-blank-line", " #[ |]#\nb", "I<esc>", "#[ |]# \nb"),
    # A range that reaches the end of a file that ends in a line break.
    # A selected line break is written twice, and the second is dropped.
    Case("a-at-the-end", "a#[\n|]#", "a<esc>", "a#[\n|]#\n\n"),
    Case("A", "a#[b|]#c\nd", "Ax<esc>", "abcx#[\n|]#d"),
    Case("o", "a#[b|]#c", "ox<esc>", "abc\nx#[|]#"),
    # Below the range's last character: on the empty line after the last
    # line break that is the line above it.
    Case("o-under-the-last-line", "#[\n|]#", "jo<esc>", "\n#[\n|]#"),
    Case("o-below-a-selection", "#[a\nb|]#\nc", "o<esc>", "a\nb\n#[\n|]#c"),
    # The indent in whole levels: one space is none.
    Case("o-a-space", "#[ |]#\n", "ox<esc>", " \nx#[\n|]#"),
    Case("O", "a#[b|]#c", "Ox<esc>", "x#[\n|]#abc"),
    Case("yp", "#[a|]#bc", "yp", "a#[a|]#bc"),
    Case("yP", "a#[b|]#c", "yP", "a#[b|]#bc"),
    Case("P-leaves-select", "#[a|]#b", "vP", "#[a|]#b"),
    Case("r", "#[ab|]#c", "rx", "#[xx|]#c"),
    Case("~", "#[aB|]#c", "~", "#[Ab|]#c"),
    # The selection stays where it was.
    Case("J", "#[a|]#bc\ndef", "J", "#[a|]#bc def"),
    # A line of nothing but blanks joins with no space.
    Case("J-blank-line", "#[a|]#b\n  \ncd", "J", "#[a|]#b\ncd"),
    Case("A-J", "#[a|]#b\ncd", "<A-J>", "ab#[ |]#cd"),
    Case("A-J-blank-line", "#[a|]#\n\nb", "<A-J>", "#[a|]#\nb"),
    Case("u", "#[a|]#bc", "du", "#[a|]#bc"),
    Case("U", "#[a|]#bc", "duU", "#[b|]#c"),
    # Helix indents a document the way it is already indented, and plain
    # text with no indent at all with a tab. This one has four spaces.
    Case(">", "    x\n#[a|]#bc", ">", "    x\n    #[a|]#bc"),
    Case(">-blank-line", "    x\n#[\n|]#y", ">", "    x\n#[\n|]#y"),
    Case(">-leaves-select", "    x\n#[a|]#bc", "v>", "    x\n    #[a|]#bc"),
    Case("ms(", "#[ab|]#c", "ms(", "#[(ab)|]#c"),
    Case("md(", "(a#[b|]#c)", "md(", "a#[b|]#c"),
    # A character that is no bracket surrounds as itself, on both sides.
    Case("ms-any", "#[a|]#", "msw", "#[waw|]#"),
    Case("ms-b", "#[a|]#", "msb", "#[bab|]#"),
    Case("md-any", "wa#[b|]#w", "mdw", "a#[b|]#"),
    Case("mr-any", "(a#[b|]#)", "mr(w", "wa#[b|]#w"),
    Case("mr([", "(a#[b|]#c)", "mr([", "[a#[b|]#c]"),
    # Leaving insert puts each cursor on what follows what was typed.
    Case("s then c", "#[a b a|]#", "sa<ret>cx<esc>", "x#[ |]#b x#(|)#"),
]
