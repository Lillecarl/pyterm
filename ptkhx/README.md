# ptkhx

> This repository is a copy. Work on ptkhx happens in
> [pyterm](https://github.com/Lillecarl/pyterm), which exports its `ptkhx/`
> directory here on every push. Send changes there, and issues to
> [Lillecarl/pymux](https://github.com/Lillecarl/pymux/issues).
> The docs are at <https://lillecarl.github.io/ptkhx/>.

<!-- The lines above are pyterm's nix/shared/readme-head.md, written by sync-sources. -->

Helix's modal editing for a prompt_toolkit buffer: normal, insert and
select modes, multiple cursors, registers, `s` to select by regex, and
the `m` surround and textobject menu.

`ptkhx.Editor` is the editor itself, and it imports nothing but the
standard library. It takes a key at a time and returns a `Request` for
what only its host can do: accept the line, walk history, complete.

The keymap tests are written in Helix's own notation, `#[foo|]#` for a
selection with its head after `foo`, so a case from Helix's own tests
reads the same here. `checks.ptkhx-oracle` runs each case through real
Helix too, and compares.

<!-- The lines below are pyterm's nix/shared/readme-tail.md, written by sync-sources. -->

## Building

    nix build github:Lillecarl/ptkhx    # from this repository alone
    nix build --file . ptkhx            # in a checkout of pyterm

The suites that judge it run in pyterm, as `checks.ptkhx-*`.

## The collection

ptkhx is one source of [pyterm](https://github.com/Lillecarl/pyterm), and
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
