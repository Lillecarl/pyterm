# fairclock

> This repository is a copy. Work on fairclock happens in
> [pyterm](https://github.com/Lillecarl/pyterm), which exports its `fairclock/`
> directory here on every push. Send changes there, and issues to
> [Lillecarl/pyterm](https://github.com/Lillecarl/pyterm/issues).
> The docs are at <https://lillecarl.github.io/fairclock/>.

<!-- The lines above are pyterm's nix/shared/readme-head.md, written by sync-sources. -->

Deadlines and stopwatches that count only the time a process could run.

On a loaded machine, a process that is ready to run can wait seconds for
a CPU, and a wall clock counts those seconds against it. Linux keeps,
per thread, the time it sat on a run queue. A fairclock deadline moves
out by that much, and a stopwatch leaves it out. Where nobody keeps
that number, as on macOS, every deadline is a wall-clock one.

- `fairclock.Deadline` and `fairclock.Stopwatch`, for a loop that polls.
- `fairclock.anyio`, `fairclock.asyncio` and `fairclock.trio`, a plain
  `with` in place of each library's own timeout.
- `fairclock.subprocess.run`, `subprocess.run` with a fair timeout.

However loaded the machine, a deadline ends by ten times its seconds.
It imports the standard library alone. Lillecarl/pyterm#1000.

<!-- The lines below are pyterm's nix/shared/readme-tail.md, written by sync-sources. -->

## Building

    nix build github:Lillecarl/fairclock    # from this repository alone
    nix build --file . fairclock            # in a checkout of pyterm

The suites that judge it run in pyterm, as `checks.fairclock-*`.

## The collection

fairclock is one source of [pyterm](https://github.com/Lillecarl/pyterm), and
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
| [fairclock](https://lillecarl.github.io/fairclock/) | deadlines that leave the machine's load out |

[pyterm's site](https://lillecarl.github.io/pyterm/) holds every source's
docs.
