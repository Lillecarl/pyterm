# pyterm

A glorified git submodule collection. There is no code of its own here. What it
holds is four repositories that are worked on together, a nix expression that
builds each of them from its checkout, and the wiring that keeps the four in
step.

| submodule | branch | upstream |
| --- | --- | --- |
| `pymux` | `graphics-protocol` | prompt-toolkit/pymux |
| `ptterm` | `graphics-protocol` | prompt-toolkit/ptterm |
| `pyte` | `graphics-protocol` | selectel/pyte |
| `prompt-toolkit` | `render-performance` | prompt-toolkit/python-prompt-toolkit |
| `umbrella` | `main` | Lillecarl/umbrella |

Each submodule carries its own `default.nix`. That file holds the package and
the tests that judge it, and nothing else. Sibling packages arrive as arguments
rather than paths, so a submodule built on its own takes its dependencies from
nixpkgs, and built here it takes the checkouts next to it. Nothing in a
submodule points back at this repository.

This repository owns the assembly. It decides which checkout answers for
`ptterm`, it names the tests, and it holds the dev shell.

## Getting a checkout

    git clone --recurse-submodules git@github.com:Lillecarl/pyterm.git
    cd pyterm
    umbrella initjj      # or initgit, if you would rather drive them with git

`--recurse-submodules` is optional: `umbrella initjj` checks out whatever is
missing. It also colocates each submodule as a jj repository and installs the
hooks described below.

## Building

    nix build --file . pymux    # or pyte, ptterm, prompt-toolkit, umbrella
    nix-shell                   # pymux, umbrella and the test dependencies

`default.nix` is the whole definition. `shell.nix` and `flake.nix` only call
into it, and the flake takes nixpkgs as its one input. Everything else comes
from the submodules.

Builds read the submodule working copies, so an edit in any of them builds
without a commit or a push.

**A flake build has to ask for the submodules by name.** Flakes see only what
git tracks, and a submodule's contents are not that, so a plain `nix build .#`
fails with "Path 'prompt-toolkit' ... is not tracked by Git":

    nix build '.?submodules=1#pymux'

A build from a file has no such problem, and it reads the working copies rather
than the last commit, which is usually what you want while working.

## Tests

A package exposes its own tests through `passthru.checks`. This repository gives
them names, because a test of ptterm against kitty is a test of ptterm, and the
run needs the ptterm that this collection assembled:

    nix build --file . checks.pyte
    nix build --file . checks.ptterm        # against kitty and libvterm
    nix build --file . checks.pymux
    nix build --file . checks.pymux-pty     # a real pty, a server and a client
    nix build --file . checks.pymux-esctest # the conformance suite, in a pane

Every run happens in the build sandbox. The ptys, the sockets and the processes
live and die inside it, so nothing of a run reaches the machine.

Several of them read the environment. That needs impure evaluation, which a
build from a file does and a flake does not:

    PYMUX_TESTS=tests/test_sixel_encoder.py nix build --file . checks.pymux
    PTTERM_FUZZ=20000 nix build --file . checks.ptterm-fuzz
    PYMUX_ESCTEST_INCLUDE=BSTests nix build --file . checks.pymux-esctest

`checks.ptterm-fuzz` hunts for deviations between ptterm and kitty. It is not a
gate: it finds them faster than they get fixed, and each one needs a decision
about whether to follow kitty or xterm. `nix flake check` leaves it out.

`checks.pymux-esctest` runs [esctest2][esctest2] in a pane. The suite judges a
terminal from the inside, and most of it fails, because a pane is not xterm.
Each failure names a real difference, and `pymux/tests/esctest-failures.txt`
records them all. The check compares a run with that list and complains at a
difference in either direction, so a regression and a fix are both visible.
Write the list again after fixing something:

    PYMUX_ESCTEST_RECORD=1 nix build --file . checks.pymux-esctest
    cp result/failures.txt pymux/tests/esctest-failures.txt

The result also holds `esctest.log`, which says why each test failed.
Narrow the run to read the reasons for one group:

    PYMUX_ESCTEST_INCLUDE=ChangeColorTests PYMUX_ESCTEST_RECORD=1 \
        nix build --file . checks.pymux-esctest

[esctest2]: https://github.com/ThomasDickey/esctest2

## umbrella

[umbrella](https://github.com/Lillecarl/umbrella) is what makes a collection
like this workable. The problem it solves is small and sharp: this repository
records one commit per submodule, and if it records a commit that no remote has,
every clone breaks on it. That is easy to do by accident, and with jj it is the
default path, because a jj bookmark does not move when you commit.

    umbrella status             # what each submodule is doing
    umbrella status --fetch     # the same, current about the remotes
    umbrella land -p -m "..."   # push the submodules, then record the pointers
    umbrella sync               # move the submodules onto the recorded pointers
    umbrella wts add spike      # the whole collection again, sharing storage
    umbrella wts rm spike

`land` is the one to reach for. It moves each submodule's branch onto the commit
being published, pushes it, and only then records the pointer here. `-p` pushes
this repository too. The order is the whole point: a submodule commit reaches
its remote before anything names it.

Two git hooks enforce the same rule for anything that does not go through
`land`. `pre-commit` refuses to stage a pointer no remote branch contains, and
`pre-push` refuses to push this repository while any pointer it carries is
private. `pre-push` fetches first, so its answer is current.

`wts` is a worktreespace: one more working copy of the whole collection, made as
jj workspaces or git worktrees depending on the mode. It shares storage rather
than cloning, so making one costs about a second and a few hundred kilobytes.

## umbrella is a submodule too

It is the tool that checks the submodules out, so a clone made without them has
to build it anyway. `default.nix` handles that with a branch: it uses the
`umbrella` checkout when the directory is there, and falls back to the commit it
pins on GitHub when it is not.

So editing umbrella needs nothing special. Change a file in `umbrella/` and
`nix build --file . umbrella` reads it, the same as any other submodule.

Moving the fallback is the one manual step. Change `rev` in `default.nix`, set
`hash` to `lib.fakeHash`, move the `umbrella` checkout out of the way, run
`nix build --file . umbrella`, and paste back the hash nix reports.
