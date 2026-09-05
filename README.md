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

Each submodule's `default.nix` holds its package alone. The suites that judge
it live in that repository's `nix/checks.nix`, which declares its own inputs,
so a package definition does not name the six terminal emulators and two
display servers that only a test needs.

Builds read the submodule working copies, so an edit in any of them builds
without a commit or a push.

**A flake is not first class here.** `flake.nix` exposes the packages so that
somebody can install pymux with one command, and nothing else. The checks and
the dev shell are not there on purpose: a flake evaluates purely, so the knobs
below that narrow a run would be invisible to it. Build and test from the file.

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

    nix build --file . checks.pyte-unit
    nix build --file . checks.ptterm-unit   # nothing but python
    nix build --file . checks.ptterm-panel  # against the other six terminals
    nix build --file . checks.ptterm-xcms   # colour specs, against the real Xlib
    nix build --file . checks.ptterm-esctest # the conformance suite, on a pty
    nix build --file . checks.ptterm-vterm  # the test suite of libvterm
    nix build --file . checks.pymux-unit
    nix build --file . checks.pymux-pty     # a real pty, a server and a client
    nix build --file . checks.pymux-integrated # the same, in one process
    nix build --file . checks.pymux-esctest # the conformance suite, in a pane
    nix build --file . checks.pymux-pictures # a picture of a real terminal
    nix build --file . checks.all            # every one that is a gate

Every run happens in the build sandbox. The ptys, the sockets and the processes
live and die inside it, so nothing of a run reaches the machine.

### A check is two derivations

Nix takes the output of a build that failed away. So a suite that fails the
build leaves nothing to look at, and every artifact it made has to be fetched
by running it again. That is backwards: the run that failed is the one whose
output somebody wants.

So `checks.<name>` is the **verdict**, and `checks.<name>.run` is the **run**
it judges. The run does not fail because the suite failed; its output holds the
log, whatever the suite wrote, and `status`, the exit code. The verdict reads
`status`, fails when it is not zero, prints the tail of the log and names the
run.

    nix build --file . checks.pymux-esctest.run
    less result/esctest.log

The run can still fail, and must. Only the exit code of the suite is caught:
setup runs before the guard, so a missing input is still loud.

One cost, and it is real: a red run is a build that succeeded, so nix caches
it. Running it again gives the same stored failure until an input changes.
`--rebuild` is the way to make it run again.

`checks.all` is every gate at once, and `checks.all.run` is the report: each
suite's output linked by name, and a summary of how each one ended. The fuzz
hunt is left out of it, because it is not a gate.

### Narrowing a run

Several checks read the environment. That needs impure evaluation, which a
build from a file does and a flake does not:

    PYMUX_TESTS=tests/test_sixel_encoder.py nix build --file . checks.pymux-unit
    PTTERM_TESTS=tests/test_scroll.py nix build --file . checks.ptterm-unit
    PTTERM_FUZZ=20000 nix build --file . checks.ptterm-fuzz
    PYMUX_ESCTEST_INCLUDE=BSTests nix build --file . checks.pymux-esctest
    PTTERM_ESCTEST_INCLUDE=BSTests nix build --file . checks.ptterm-esctest
    PTTERM_VTERM_INCLUDE=movecursor nix build --file . checks.ptterm-vterm
    PYMUX_PICTURES=underlines nix build --file . checks.pymux-pictures

The suite of ptterm is three checks, split by what each test needs. About forty
of its sixty files need nothing but python, and `checks.ptterm-unit` is those:
it is the one to run while working, and it pays for none of the emulators.

`checks.ptterm-panel` reads a screen back from kitty, libvterm, WezTerm,
Alacritty, Ghostty and xterm.js, and judges the screen of ptterm against them.
`checks.ptterm-xcms` starts an Xvfb and reads a colour spec with the real Xlib,
because the colour parser of ptterm is a port of the colour management of Xlib
and only the original says whether the port is right.

No file is listed anywhere. A test belongs to the group whose oracle it
imports, and `ptterm/tests/conftest.py` reads that from the source before
pytest imports anything. So a new test lands in the right group by writing the
import it needs. Nothing in the unit group may skip, because a test that needs
an oracle and lands there would find nothing, skip, and pass in silence.

`checks.pymux-pty` and `checks.pymux-integrated` run the same end to end test
over the two routes that carry the packets between a client and a server. The
first one starts a server daemon on a unix socket and attaches a client to it.
The second one runs `pymux integrated`, where the server and the client are one
process and the packets go through queues. A client that connects to a socket
reaches whatever server holds it, which can be an older build; the integrated
client reaches the server that the command started and nothing else. The two
runs together say which side a fault is on.

`checks.pymux-pictures` is the only check that gets past the cell. It runs a
real terminal emulator on a display server of its own, plays a program in it
twice — once bare and once in a pymux pane that covers every cell — and
subtracts one screenshot from the other. Two bugs got past every other check we
have that way: a cursor stopped blinking, and an underline appeared where none
belonged. Its result is a directory, so a run always leaves its pictures behind
at `result/<terminal>/<fixture>/{bare,pymux,difference}.png`.

It runs two seats. xterm speaks X and nothing else, so there is an Xvfb. foot
speaks Wayland and nothing else, so there is a [cage](https://www.hjdskes.nl/projects/cage/),
a kiosk compositor that gives its one window the whole output. Wayland is the
better shape for this work: one window, no decoration, nothing to find, and
`grim` takes the output. The X seat has to find its window among the ones that
ran before it.

Two terminals are never compared against each other. Each draws its own glyphs
from its own font stack, so a difference between two of them says nothing.
What a second terminal adds is a second opinion on whether pymux changes what
that terminal draws.

### Reproducing a fault that only happens on your machine

A fixture written by hand can only hold what somebody thought to write, and
some programs cannot run in a build sandbox at all. Claude Code needs a login,
a project and your own configuration, and what it draws depends on all three.

So record it once, where it goes wrong, and replay the bytes:

    ptterm-record --into pymux/tests/recordings --lines 24 --columns 80 \
        claude -- claude

`ptterm-record` comes with ptterm, so it runs anywhere. The program behaves
normally: use it, reproduce the fault, and quit. A `claude.bin` in
`pymux/tests/recordings` then becomes a fixture called `recorded-claude`, and
`checks.pymux-pictures` plays it back bare and in a pane and subtracts the two
pictures.

    PYMUX_PICTURES=recorded-claude nix build --file . checks.pymux-pictures.run

**Read a recording before you commit it.** It holds whatever was on the
screen. `pymux/tests/recordings/README.md` says the rest.

Not every difference is a fault. A pane reads what a program asked for and
writes the request again in the form the terminal understands, so a pane can
draw more than that terminal draws on its own. xterm ignores `CSI 4:1 m` and
draws no underline; a pane turns the same request into `CSI 4 m`, which it does
draw, so 206 pixels differ there. foot reads the colon form itself, and its two
pictures are the same. Two seats, one answer: the difference belongs to xterm.
`pymux/tests/picture-differences.txt` records each difference that stands and
says why, and a run is judged against that list, so a regression and a fix are
both visible. Every run writes the list it saw beside its pictures, so writing
the list again is one command:

    nix build --file . checks.pymux-pictures.run
    cp result/picture-differences.txt pymux/tests/picture-differences.txt

`checks.ptterm-fuzz` hunts for deviations between ptterm and kitty. It is not a
gate: it finds them faster than they get fixed, and each one needs a decision
about whether to follow kitty or xterm. `checks.all` leaves it out.

[esctest2][esctest2] judges a terminal from the inside: it runs as a program in
that terminal, writes control sequences and reads the reports that come back.
Two checks run it, and the difference between them is the point.

`checks.ptterm-esctest` runs it on a pty of its own, with ptterm as the
terminal and nothing else around it. Five tests fail, and each names a real
difference between ptterm and xterm. `ptterm/tests/esctest-failures.txt`
records them.

`checks.pymux-esctest` runs it in a pane. Nine fail, because a pane is not a
window: it has no printer, no locator and no window to move, and its size comes
from the layout and not from the program inside it.
`pymux/tests/esctest-failures.txt` records those.

So what fails in a pane and not on a pty is what pymux puts around the
emulator, and what fails in both belongs to ptterm.
`ptterm/tests/DEVIATIONS.md` says what each name is.

Three tests run in neither. `NOT_OURS` in each driver names them: they ask
where the window is and whether it is iconified, and neither a widget nor a
pane has one. A pattern there that matches no test fails the check, so an
exclusion cannot go stale in silence.

Each check compares a run with its own list and complains at a difference in
either direction, so a regression and a fix are both visible. Every run writes
the list it saw and the log that says why, so reading the reasons and writing
the list again are the same command:

    nix build --file . checks.pymux-esctest.run
    less result/esctest.log
    cp result/failures.txt pymux/tests/esctest-failures.txt

A narrowed run is judged too. A name in the list that the regular expression
does not choose was never going to run, so it does not count as missing:

    PYMUX_ESCTEST_INCLUDE=ChangeColorTests \
        nix build --file . checks.pymux-esctest.run

[esctest2]: https://github.com/ThomasDickey/esctest2

### The test suite of libvterm

`checks.ptterm-vterm` is the other way round from a judge. libvterm already
answers for ptterm in `checks.ptterm-panel`: the same bytes go into both and
the two screens are compared. libvterm also ships 43 test files and a runner
that drives them against any program, so its suite can judge ptterm.

Nothing in libvterm changes. `t/run-test.pl` takes the program to drive, and
`ptterm/tests/vterm_harness.py` is that program: it speaks the protocol of
`t/harness.c` with ptterm behind it.

A file is the unit that can be left out. The runner compares the lines a
harness emits against the lines a file expects, in order, so a harness that
stays quiet cannot skip. 27 files are left out by name, and each reason says
why the question does not apply: libvterm reports every glyph it lays down and
which rectangle it redrew, and ptterm has neither. `NOT_OURS` in
`ptterm/tests/drive_with_vterm.py` holds the names, and a pattern there that
matches no file fails the check.

The 16 that are left hold 270 assertions about the state: where the cursor is,
what the screen holds, and what style the next character takes. 23 answers
differ, and `ptterm/tests/vterm-failures.txt` records them the same way the
conformance lists do.

    PTTERM_VTERM_INCLUDE=movecursor nix build --file . checks.ptterm-vterm.run
    less result/vterm.log
    cp result/failures.txt ptterm/tests/vterm-failures.txt

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
