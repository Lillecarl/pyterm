# txterm

A terminal widget for [Textual]. It runs a program on a pty and draws
what the program writes.

```python
from textual.app import App, ComposeResult
from txterm import Terminal

class Shell(App):
    def compose(self) -> ComposeResult:
        yield Terminal(["bash"])

Shell().run()
```

Or one program in one window, from a shell:

```sh
txterm htop
```

## What is in it

- `Terminal` — the widget. It owns a screen and a pty, sizes both,
  draws the rows as Rich segments, and sends the keys.
- `TerminalApp` — a whole application that is one terminal. It exists
  to be driven by a suite that needs a program and not a widget.
- `style.py` — how Rich spells a cell.
- `keys.py` — what a key of Textual sends.

## Where the rest of it is

txterm draws and reads keys. Everything else already had a home:

| | job |
| --- | --- |
| `pyte` | parse, and hold a screen |
| `ptyhost` | run a program and carry its bytes |
| `ptterm` | draw it with prompt-toolkit |
| `txterm` | draw it with Textual |
| `pymux` | arrange several of them |

`Lillecarl/pymux#82` holds the argument, and `#11` the four layers.

**The parser is in `ptterm` today, and it should be in `pyte`.** That
layer imports no toolkit at all, so nothing of prompt-toolkit comes into
this package with it, and `tests/test_the_layers.py` holds that. The
same file names every module of `ptterm` this package touches. That list
is the move: when the pure layer reaches `pyte`, it is the list to carry
and the imports here to rewrite.

## What Rich cannot draw

A cell holds what SGR said, and three of those things have no field in
a `rich.style.Style`. `style.py` says so at the top:

- the shape of an underline, other than single and double;
- the colour of that underline;
- superscript and subscript.

The screen still holds them, and a program can still read them back.

[Textual]: https://github.com/Textualize/textual
