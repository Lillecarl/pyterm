# txterm

> This repository is a copy. Work on txterm happens in
> [pyterm](https://github.com/Lillecarl/pyterm), which exports its `txterm/`
> directory here on every push. Send changes there, and issues to
> [Lillecarl/pymux](https://github.com/Lillecarl/pymux/issues).
> The docs are at <https://lillecarl.github.io/txterm/>.

<!-- The lines above are pyterm's nix/shared/readme-head.md, written by sync-sources. -->

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

**A `Terminal` refuses a resize.** A program asks for one with DECSLPP,
DECCOLM or XTWINOPS, and a widget cannot take room from the widgets
beside it, so the answer is no and the modes that need it go away. An
application that will really move the widget passes `may_resize` and
`resize_func` and answers for itself.

## Where the rest of it is

txterm draws and reads keys. The screen and the parser are in `pyte`,
and the pty is in `ptyhost`. `tests/test_the_layers.py` names every
module of `pyte` this package imports, and holds that nothing of
prompt-toolkit comes in behind them. Lillecarl/pymux#82 holds the
argument.

## What Rich cannot draw

A cell holds what SGR said, and three of those things have no field in
a `rich.style.Style`. `style.py` says so at the top:

- the shape of an underline, other than single and double;
- the colour of that underline;
- superscript and subscript.

The screen still holds them, and a program can still read them back.

[Textual]: https://github.com/Textualize/textual

<!-- The lines below are pyterm's nix/shared/readme-tail.md, written by sync-sources. -->

## Building

    nix build github:Lillecarl/txterm    # from this repository alone
    nix build --file . txterm            # in a checkout of pyterm

The suites that judge it run in pyterm, as `checks.txterm-*`.

## The collection

txterm is one source of [pyterm](https://github.com/Lillecarl/pyterm), and
each source claims one job:

| source | job |
| --- | --- |
| [pyte](https://lillecarl.github.io/pyte/) | parse, and hold a screen |
| [ptyhost](https://lillecarl.github.io/ptyhost/) | run a program on a pty, and carry its bytes |
| [ptterm](https://lillecarl.github.io/ptterm/) | draw one terminal, with prompt-toolkit |
| [txterm](https://lillecarl.github.io/txterm/) | draw one terminal, with Textual |
| [pymux](https://lillecarl.github.io/pymux/) | arrange several of them |
| [pysmithay](https://lillecarl.github.io/pysmithay/) | a headless Wayland compositor, for a GUI program in a pane |
| [pyterm-pytest](https://lillecarl.github.io/pyterm-pytest/) | the test equipment the suites share |
| [deferimport](https://lillecarl.github.io/deferimport/) | make imports lazy, without a keyword |
| [ptkhx](https://lillecarl.github.io/ptkhx/) | Helix's modal editing, for a prompt_toolkit buffer |

[pyterm's site](https://lillecarl.github.io/pyterm/) holds every source's
docs.
