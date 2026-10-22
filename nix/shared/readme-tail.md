<!-- The lines below are pyterm's nix/shared/readme-tail.md, written by sync-sources. -->

## Building

    nix build github:Lillecarl/@name@    # from this repository alone
    nix build --file . @name@            # in a checkout of pyterm

The suites that judge it run in pyterm, as `checks.@name@-*`.

## The collection

@name@ is one source of [pyterm](https://github.com/Lillecarl/pyterm), and
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
