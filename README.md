# pyterm

A glorified git submodule collection. There is no code of its own here. What it
holds is six repositories that are worked on together, a nix expression that
builds each of them from its checkout, and the wiring that keeps the six in
step.

| submodule | branch | upstream | job |
| --- | --- | --- | --- |
| `pymux` | `graphics-protocol` | prompt-toolkit/pymux | arrange several terminals |
| `ptterm` | `graphics-protocol` | prompt-toolkit/ptterm | draw one with prompt-toolkit |
| `txterm` | `main` | Lillecarl/txterm | draw one with Textual |
| `ptyhost` | `main` | Lillecarl/ptyhost | run a program and carry its bytes |
| `pyte` | `graphics-protocol` | selectel/pyte | parse, and hold a screen |
| `prompt-toolkit` | `render-performance` | prompt-toolkit/python-prompt-toolkit | the toolkit under it all |
| `umbrella` | `main` | Lillecarl/umbrella | hold the others together |

Each submodule carries its own `default.nix`. That file holds the package and
the tests that judge it, and nothing else. Sibling packages arrive as arguments
rather than paths, so a submodule built on its own takes its dependencies from
nixpkgs, and built here it takes the checkouts next to it. Nothing in a
submodule points back at this repository.

This repository owns the assembly. It decides which checkout answers for
`ptterm`, it names the tests, and it holds the dev shell.

**`docs/the-model.md` says what the six are, in one place**: the words we use
for each thing, what each layer holds, and how one keystroke and one frame
travel through all of them. Read it before a conversation about architecture,
because several words here mean two things -- "window", "screen", "layout" and
"terminal" each name something in pymux and something else in prompt_toolkit.

## Getting a checkout

    git clone --recurse-submodules git@github.com:Lillecarl/pyterm.git
    cd pyterm
    umbrella initjj      # or initgit, if you would rather drive them with git

`--recurse-submodules` is optional: `umbrella initjj` checks out whatever is
missing. It also colocates each submodule as a jj repository and installs the
hooks described below.

**`.gitmodules` names the submodules over https, and it has to.** Nix follows
those URLs when a flake asks for `?submodules=1`, whatever the URL of this
repository was, so an SSH URL there makes every one of them need a key. A
machine without one -- CI, a fresh container, somebody else's laptop -- then
cannot evaluate a configuration that pins pyterm at all, which is most of what
the home-manager module below is for.

If you push to these repositories, tell git to send https to SSH once:

    git config --global url."git@github.com:".pushInsteadOf "https://github.com/"

Fetching stays anonymous and pushing goes over your key. A checkout that
already exists keeps the remotes it has; only a fresh clone reads these URLs.

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

**A flake is not first class here.** `flake.nix` exposes the packages and the
home-manager module, so that somebody can install pymux with one command and
configure it, and nothing else. The checks and the dev shell are not there on
purpose: a flake evaluates purely, so the knobs below that narrow a run would
be invisible to it. Build and test from the file.

Neither of those two is defined there. Both are attributes of `default.nix`
that the flake passes through, so a person with no flake reaches the same
things.

**A flake build has to ask for the submodules by name.** Flakes see only what
git tracks, and a submodule's contents are not that, so a plain `nix build .#`
fails with "Path 'prompt-toolkit' ... is not tracked by Git":

    nix build '.?submodules=1#pymux'

A build from a file has no such problem, and it reads the working copies rather
than the last commit, which is usually what you want while working.

## Configuring pymux with home-manager

pymux reads `$XDG_CONFIG_HOME/pymux/pymux.conf` at startup, and `~/.pymux.conf`
after it: one command per line, the shape of
`pymux/examples/example-config.conf`. `nix/home-manager.nix` writes the first
of those, so it is generated and not placed by hand.

It is a plain module file, so a path is the whole import:

    imports = [ /path/to/pyterm/nix/home-manager.nix ];

`flake.nix` names the same file as `homeManagerModules.default`, for a person
who takes this repository as a flake input:

    pyterm.url = "git+https://github.com/Lillecarl/pyterm?submodules=1";

`?submodules=1` matters here too. The default of the module's `package` option
builds pymux out of the source the module came from, and a flake without the
submodules has no source to build.

Two options carry the configuration:

    programs.pymux = {
      enable = true;
      settings = {
        prefix = "C-a";
        base-index = 1;
        mode-keys = "vi";
        status-left = "[#h:#S] ";
      };
      extraConfig = ''
        bind-key "|" split-window -h
        bind-key "-" -- split-window -v
      '';
    };

`settings` writes one `set-option` line for each entry, under pymux's own
names, which are the ones in `pymux/pymux/options.py`. There is no typed
option per setting, because that list already exists and a second one here
would go stale. `true` and `false` become `on` and `off`, a number becomes
itself, a string is quoted, and `null` writes no line at all.

`extraConfig` is added after the settings. Key bindings go there: `bind-key`
takes a command and its own arguments, and a Nix option cannot spell that
better than the line itself does.

### How a key is written

Either way. `C-a` is the spelling tmux uses, and `ctrl+a` is the chord
spelling, where `+` joins the keys pressed together. `bind-key`, `send-keys`
and the `prefix` option all read both.

The chord spelling reaches keys the other one cannot name. `ctrl+home`,
`shift+f5` and `ctrl+shift+end` are three, and there are twenty-two more:
tmux's table here writes out ctrl on the four arrows and on no other key
that a terminal spells out. `send-keys C-Home` used to type the six letters
into the pane, because a name that reads as nothing is sent as the text it is.

    bind-key ctrl+home  send-keys C-Home
    send-keys ctrl+shift+end
    send-keys escape a            # two presses, in order

`pymux/pymux/key_spelling.py` holds the grammar, and
`pymux/tests/test_key_spelling.py` walks every name the older spelling reaches
and re-spells it, so the two say the same thing.

`compose-key` opens a box that completes those names and sends the key to the
pane. It is for a keyboard that cannot type the key at all: a laptop with no
Home key, no Insert and no function row. It has no key of its own, so bind one:

    bind-key k compose-key

`checks.pyterm-home-manager` judges the module. Nix writes the file it
generates, and pymux reads it through the same `source-file` a real startup
runs, then says what each value became.

## Tests

A package exposes its own tests through `passthru.checks`. This repository gives
them names, because a test of ptterm against kitty is a test of ptterm, and the
run needs the ptterm that this collection assembled:

    nix build --file . checks.pyte-unit     # the screen, and nothing but python
    nix build --file . checks.pyte-xcms     # colour specs, against the real Xlib
    nix build --file . checks.ptyhost-unit  # real programs on real ptys
    nix build --file . checks.ptterm-unit   # nothing but python
    nix build --file . checks.ptterm-panel  # against seven other terminals
    nix build --file . checks.ptterm-esctest # the conformance suite, on a pty
    nix build --file . checks.ptterm-vterm  # the test suite of libvterm
    nix build --file . checks.ptterm-vttest # every screen vttest draws
    nix build --file . checks.ptterm-instructions # what parsing costs, in instructions
    nix build --file . checks.ptterm-footprint # what a scrollback costs to hold
    nix build --file . checks.txterm-unit   # the Textual widget, drawn and driven
    nix build --file . checks.txterm-esctest # the same suite, in a Textual pane
    nix build --file . checks.pymux-unit
    nix build --file . checks.pymux-frame   # what a frame costs, in instructions
    nix build --file . checks.pymux-leaks   # what is still alive after a teardown
    nix build --file . checks.pymux-keystroke # a keystroke, in instructions
    nix build --file . checks.pymux-latency # the same keystroke, in milliseconds
    nix build --file . checks.pymux-turns   # the same keystroke, in loop turns
    nix build --file . checks.pymux-profile # where the time of a frame goes
    nix build --file . checks.pymux-pty     # a real pty, a server and a client
    nix build --file . checks.pymux-integrated # the same, in one process
    nix build --file . checks.pymux-esctest # the conformance suite, in a pane
    nix build --file . checks.pymux-vterm   # the same libvterm suite, through pymux
    nix build --file . checks.pymux-pictures # a picture of a real terminal
    nix build --file . checks.pymux-vttest-pictures # the same, of vttest
    nix build --file . checks.pyterm-home-manager # the module, judged by pymux
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
suite's output linked by name, and a summary of how each one ended. Four are
left out of it, and none of the four is a gate: the fuzz hunt, the vttest
walk, the pictures of vttest, and the roaming property tests.

### Narrowing a run

Several checks read the environment. That needs impure evaluation, which a
build from a file does and a flake does not:

    PYMUX_TESTS=tests/test_sixel_encoder.py nix build --file . checks.pymux-unit
    PYTE_TESTS=tests/test_scroll.py nix build --file . checks.pyte-unit
    PROMPT_TOOLKIT_TESTS=tests/test_layout.py nix build --file . checks.prompt-toolkit-unit
    PTTERM_TESTS=tests/test_the_widget.py nix build --file . checks.ptterm-unit
    TXTERM_TESTS=tests/test_drawing.py nix build --file . checks.txterm-unit
    PTTERM_FUZZ=20000 nix build --file . checks.ptterm-fuzz
    PYMUX_PTY_CHECKS=a_pane_that_changes_nothing nix build --file . checks.pymux-pty
    PYMUX_ESCTEST_INCLUDE=BSTests nix build --file . checks.pymux-esctest
    PTTERM_ESCTEST_INCLUDE=BSTests nix build --file . checks.ptterm-esctest
    TXTERM_ESCTEST_INCLUDE=BSTests nix build --file . checks.txterm-esctest
    PTTERM_VTERM_INCLUDE=movecursor nix build --file . checks.ptterm-vterm
    PTTERM_VTTEST_INCLUDE='^4 ' nix build --file . checks.ptterm-vttest.run
    PYMUX_VTERM_INCLUDE=unicode nix build --file . checks.pymux-vterm
    PYMUX_PICTURES=underlines nix build --file . checks.pymux-pictures
    PYMUX_VTTEST_INCLUDE='^9 ' nix build --file . checks.pymux-vttest-pictures
    PYMUX_VTTEST_TERMINALS=xterm,foot nix build --file . checks.pymux-vttest-pictures
    PYTE_HYPOTHESIS_SEED=1743 nix build --file . checks.pyte-roaming

**A property test draws the same examples every run here.** `checks.pyte-unit`
and `checks.pymux-unit` both load hypothesis's pinned profile, so a green gate
means the same thing twice. `checks.pyte-roaming` runs pyte's property tests
off a fresh seed and is not a gate. It takes the clock for its seed, so each
build is a new hunt, and `PYTE_HYPOTHESIS_SEED` names one that a person wants
back. pymux has no hunt of its own yet; `--hypothesis-profile=roaming` is the
same thing by hand.

**A test lives with the code it judges.** The tests that drive a screen and
read its cells back are `pyte`'s, and there are about ninety files of them:
`checks.pyte-unit` is the one to run while working on the screen, and
`checks.pyte-xcms` starts an Xvfb and reads a colour spec with the real Xlib,
because `pyte/xcms.py` is a port of the colour management of Xlib and only the
original says whether the port is right.

What is left in ptterm judges the widget. The suite is two checks, split by
what each test needs. Seventeen of its thirty-six files need nothing but
python, and `checks.ptterm-unit` is those; it pays for none of the emulators.

`checks.ptterm-panel` reads a screen back from kitty, libvterm, WezTerm,
Alacritty, Ghostty and xterm.js, and judges the screen of ptterm against them.
It also runs xterm itself, on an Xvfb of its own, and reads that screen back
with DECRQCRA. xterm answers a character and no attribute, so it takes no part
in the vote: `ptterm/tests/DEVIATIONS.md` says where it answers instead.

The three suites that drive a program on a pty stay with ptterm as well:
esctest, vttest and the test files of libvterm all read the screen back through
a real fork, so they judge a screen on a pty, and the lowest layer that has
both is the widget.

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

### The screens of vttest

[vttest][vttest] is the other conformance program of Thomas Dickey, after Per
Lindberg wrote it in 1985. It is nothing like esctest2. esctest2 reads the
screen back with DECRQCRA and judges it, so it can be a gate. vttest draws a
screen and asks a person whether what they see is right.

So `checks.ptterm-vttest` judges no screen, and `checks.all` leaves it out. It
is a walker: it enters every menu item, answers every "Push <RETURN>", and
writes down what the screen held each time.

    nix build --file . checks.ptterm-vttest.run
    less result/screens.txt

What comes out is every screen vttest can draw, with the menu path that reached
it, the size of the screen, where the cursor stood, and which rows were drawn
twice as big. That last one matters: item 4 of the main menu is entirely about
rows of double size, and every cell in one looks ordinary in a text dump.

The verdict does judge the walk itself. A run that drew nothing fails, and so
does an exclusion in `NOT_OURS` that names no menu item.

Two items need a person and `NOT_OURS` names them: the keyboard test reads keys
one at a time, and the setup menu changes what the run after it does.

**Never send a key before the prompt is on the screen.** `holdit()` in vttest's
`unix_io.c` throws away everything waiting on the input before it prints "Push
<RETURN>", so a key sent early is a key that vanishes.

### A picture of vttest

The walk above stops at the cell. It says what ptterm holds, which is not what
a terminal paints, and item 4 of vttest is exactly the case where the two come
apart: a row of double size holds ordinary cells.

`checks.pymux-vttest-pictures` gets past that. The walker also passes every
byte vttest wrote to the terminal it runs in, so vttest draws on a real
terminal while the same bytes go into the ptterm model that says when a screen
is finished. The walk then stops at each screen and a harness outside takes its
picture. It runs twice, once with a pymux pane in the chain and once without
one, and subtracts the pairs.

    nix build --file . checks.pymux-vttest-pictures.run
    ls result/xterm/bare result/xterm/pymux result/xterm/differ

The two runs have to draw the same screens or no picture of one lines up with a
picture of the other, so the check compares the two lists of menu paths first
and fails on that rather than on a pixel count. The walk is what makes that
possible: two runs of it write the same list.

xterm is the seat, which is the other way round from the pictures above. It is
the only one of the three terminals here that draws a double sized line at all:
foot draws every "ESC # 6" row ordinary and says nothing, and kitty logs
"Unhandled Esc # code" for each of them.

`tests/vttest-picture-differences.txt` records each difference that stands and
says why, and a run is judged against it in both directions.

**It is not a gate yet, and it should not be made one yet.** The chain is
proven: three runs of the default item give the same verdicts, and the first
outing found three faults that no other check here can see. The judging is not
proven. Item 2 of the main menu still flaps, because one of those faults is a
single change at a fixed moment after a screen is drawn, so whether a
measurement holds it depends on when the measurement starts. A check that
flaps is worse than no check.

[vttest]: https://invisible-island.net/vttest/

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
what the screen holds, and what style the next character takes. 15 answers
differ, and `ptterm/tests/vterm-failures.txt` records them the same way the
conformance lists do.

    PTTERM_VTERM_INCLUDE=movecursor nix build --file . checks.ptterm-vterm.run
    less result/vterm.log
    cp result/failures.txt ptterm/tests/vterm-failures.txt

### The same suite, with pymux in the middle

`checks.ptterm-vterm` judges our **model**. `checks.pymux-vterm` judges our
**wire**, and it goes one level further:

    the test file ── PUSH ──▶ a program in a full screen pane
                                       │
                                  ptterm parses
                                       │
                            pymux renders and emits
                                       │
      the test file ◀── an answer ── libvterm reads what pymux emitted

Nothing of ours answers anything. `t/harness.c` is built as it stands, a real
libvterm sits behind it, and every assertion is answered in libvterm's own
words about what came off our wire. That is what makes it worth having: a
judge holds things our model does not, so a borrowed suite can stay green on
them as long as we emit them faithfully.

It also decides which files can run, and the cut is different from the one
`ptterm` makes. **A wire carries a screen and nothing else.** `?pen` asks what
style the *next* character will take, and nothing has been drawn with it, so
it is not on the wire to be read. `?lineinfo`, the modes, the margins and the
tab stops are the same. Those are real questions, and the direct plug-in is
where they are asked.

The bytes reach the pane through a fifo, and a fence goes down it behind each
payload: an OSC 52, which ptterm hands to pymux and pymux writes to its
client. Seeing the fence on the wire proves the pane consumed the payload.
`pymux/tests/vterm_middleman.py` says the rest.

    PYMUX_VTERM_TRACE=1 nix build --file . checks.pymux-vterm.run
    less result/vterm.log

### The same middle, with Alacritty's recordings

`pymux/tests/middleman.py` holds the pane, the fifo and the fence, and nothing
in it is libvterm's. `checks.pymux-alacritty` is the second suite to use it.

Alacritty ships 45 reference tests. Each one is a recording of a real program
— vim, tmux, fish, zsh — and the grid that recording should make. Their own
`ref.rs` replays the bytes into a `Term` and compares. This puts the bytes on
the screen of a full screen pane instead, and gives what pymux emitted to a
real `Term`:

    the recording ──▶ a full screen pane ──▶ pymux emits ──▶ a real Term
                                                                  │
                              grid.json ◀── compared with ────────┘

So Alacritty's own assertion holds if we emit what the program drew, and
`alacritty_terminal` builds the grid and compares it. The judge is a second
binary in the crate the panel already builds, and the data is pinned to
`v0.17.0`, the tag carrying the `alacritty_terminal` that judge links.

**Five are left out**: they keep a scrollback, and a wire carries a screen.
Of the 40 that run, **13 differ**, recorded in
`pymux/tests/alacritty-failures.txt`. `tmux_htop`, `tmux_git_log`,
`vim_simple_edit`, `vim_24bitcolors_bce`, `fish_cc` and `zsh_tab_completion`
are among the ones that agree, cell for cell, over tens of thousands of bytes.

It is the slowest gate here: each test gets a pane of its own, because each
one names its own screen size.

    PYMUX_ALACRITTY_INCLUDE=underline nix build --file . checks.pymux-alacritty.run
    less result/alacritty.log

### What it costs, in instructions and not in seconds

`checks.ptterm-instructions` feeds 23 of the same recordings to the parser alone
and counts the **bytecode instructions** each one takes. A change that makes
ptterm much slower passes every other check here, so this is the one that
notices.

The unit is deliberate. A second belongs to the machine that measured it, and
a build sandbox runs beside other jobs, so a wall clock reading proves nothing
twice. `sys.monitoring` reports one event per bytecode instruction, and the
number is exact: the same code over the same bytes gives the same count on
every machine, under any load. `nix build --rebuild` confirms it, byte for
byte.

`ptterm/tests/instruction-budgets.txt` holds one count per recording, and a
run that moves more than 5% either way fails. A count that climbed is the
fault this gate is for; a count that fell is a budget nobody updated.

Two things move a count that is not a change in the code: the version of
Python, and the seed of the hash. The check pins `PYTHONHASHSEED`, and an
interpreter upgrade means recording the budgets again.

    PTTERM_INSTRUCTIONS_INCLUDE=vim nix build --file . checks.ptterm-instructions
    PTTERM_INSTRUCTIONS_TOLERANCE=2 nix build --file . checks.ptterm-instructions
    cp result/instruction-budgets.txt ptterm/tests/instruction-budgets.txt

### What arranging several of them costs

`checks.pymux-frame` is the same idea one layer up. That one measures what a
pane costs; this one measures what a *window* costs: laying it out, filling the
gaps with borders, and drawing the frame around the panes. One pane, four and
sixteen, in each layout, and the panes themselves are empty so that nothing of
ptterm is in the number.

One line of it is not a cost. **"(plans)" counts how many times a frame
measures where the panes are, and a frame needs one.** Everything drawn inside
a frame asks the layout the same question -- a title bar names the pane on each
side of its own, so a window of sixteen panes asks sixty-four times -- and each
of those used to measure the whole window again. That was 950k instructions
against a frame of 55k. Now the frame's plan is worked out once and read.

    PYMUX_FRAME_INCLUDE=strip nix build --file . checks.pymux-frame
    PYMUX_FRAME_TOLERANCE=2 nix build --file . checks.pymux-frame
    cp result/frame-budgets.txt pymux/tests/frame-budgets.txt

### What a scrollback costs to hold

`checks.ptterm-footprint` is the other half of the same question. The two
checks above measure what a history costs to **touch**: a linefeed, a reflow, a
frame. This measures what it costs to **keep**. A person raises `history-limit`
to read a long build log, opens sixteen panes and leaves them for a week, and
the machine either has the room or it swaps.

Bytes are a fair unit for the same reason an instruction count is. `tracemalloc`
reports what Python allocated, and the same objects on the same interpreter take
the same room on every machine. Resident memory does not: it holds the
interpreter, the arenas it has not given back, and every other job in the
sandbox.

The figure to read is **a row**, and it is marginal on purpose. A filled pane
holds the history *and* the pane, so dividing the whole by the depth charges a
row for a share of the screen, the parser and the widget's caches. The
difference between two depths is the history alone.

    plain    50000 rows   25.3 MB     540 B a row
    wrapped  50000 rows   77.6 MB     1.6 KB a row

The log also names the twelve allocation sites that hold the most, so a number
a person does not like points at a line of code. That is how
Lillecarl/pymux#227 was found: `Row` held a closure over the blank cell, which
cost more per row than the cells did.

    PTTERM_FOOTPRINT_INCLUDE=2000 nix build --file . checks.ptterm-footprint
    PTTERM_FOOTPRINT_TOLERANCE=10 nix build --file . checks.ptterm-footprint
    cp result/footprint-budgets.txt ptterm/tests/footprint-budgets.txt

### What is still alive afterwards

`checks.pymux-leaks` asks the question none of the others do: what does pymux
still hold once a pane, a window or a client has gone? A multiplexer runs for
weeks, so a pane's worth of objects kept on every `kill-pane` is a leak nobody
sees until the machine swaps.

Two questions, and the first is exact. **Is it dead?** A weak reference to every
object a round makes -- the pane, the widget, the screen, the process, the
window, the client, its application -- and after the teardown every one of them
has to be gone. That has no tolerance. `tests/what_holds_it.py` walks
`gc.get_referrers` outward and names what holds a survivor, so a red run points
at a line rather than at a program.

**Does it plateau?** Some leaks keep nothing dead: a list that grows a row per
write holds only live objects and still eats the machine. So the same work runs
twice and the count of tracked objects has to come out the same. There is no
budget file for it, because there is no legitimate growth -- a healthy type is
zero on both sides.

**A leak shows at any volume**, because the question is whether an object died
and not how many bytes it saw. So the gate feeds a little and the knobs feed a
lot. The workload is Alacritty's recordings again, through the same
`Stream.feed` a pty would call.

**Both routes run**, because a client can arrive two ways and they hold
different things. `in-process` is `Pymux.add_client`, with no socket and no
connection: it covers the panes, the screens, the windows and the layout.
`connection` puts a real `ServerConnection` over the queues of `pipes.memory`,
which is the transport of `pymux integrated`, so the background tasks, the pipe
input and the client state the server makes are all real. A round cannot tell
them apart, so a leak on one route is the same round passing on the other. The
second route found three the first could not see: a shared `AppSession`, a
restored SIGWINCH handler, and a connection the session never let go of.

    PYMUX_LEAKS_BYTES=1000000 PYMUX_LEAKS_PANES=16 PYMUX_LEAKS_ROUNDS=8 \
      nix build --file . checks.pymux-leaks     # about 350 MB
    PYMUX_LEAKS_ROUTE=connection nix build --file . checks.pymux-leaks

**One trap is worth knowing before you read a red run.** Killing a pane frees
nothing by itself: the child is reaped on the loop, the reap closes the slave
side of the pty, the master then reads the end of the file, and only then is the
reader taken off the loop. Until that last step the loop's selector holds the
callback that holds the pane. The first version of this check killed and looked
straight away, and called every pane a leak.

A detach on the `connection` route has the same shape one layer up: closing the
client end asks the connection to close, and the application it drew with stops
on a later turn of the loop. Both waits are in `tests/what_leaks.py`, and both
are the reason a red run is worth believing.

**The question is asked while the session is still standing**, which is what
makes a leak into the server visible at all. It used to be asked after the
round's `Pymux` had gone as well, so a pane left in `Arrangement.windows` or a
client left in `Pymux._client_states` died with the session and passed.

### The same keystroke, counted rather than timed

`checks.pymux-keystroke` is the gateable half of the section below. A wall clock
cannot fail a build, and bytecode can: the same code over the same bytes gives
the same count on every machine. Carl put it as "number go up = bad".

Three stages, and neither of the counters above covered two of them. **key** is
a key press through the client's key processor, into the binding, and out to the
pane's pty. **parse** is the answer arriving through `Stream.feed`. **render**
is `Renderer.render`, which lays the window out, draws it, **diffs it against
the last frame** and writes the escape sequences — the diff and the writing are
what a keystroke pays and a recording does not.

    key                 68117 instructions      468 us
    parse                 263 instructions        6 us
    render             230568 instructions     1716 us
    all of it          298948 instructions     2190 us

**A whole keystroke runs before anything is counted**, because every stage has
once-only work behind it that a keystroke does not pay: the renderer's first
frame paints the whole screen rather than one cell, and the first key press
builds the merged key bindings for the layout. Counted cold, the press came to
266,429 instructions in 468 microseconds — half a billion instructions a
second, where the render in the same run says 132 million. **A rate that is not
possible is how both of those were found**: two different pieces of work were
being compared.

**Nothing runs the event loop**, which is what makes it a gate. A loop exists,
because arming the key processor's flush timer needs one, but it never turns —
so the pane's program cannot write to the screen and no frame can change for a
reason the file did not choose. `status-right` is emptied for the same reason:
the default draws a clock, and a frame either side of a second is two diffs.

Read it against the section below. The work takes 2.1 ms here, in one process
with no socket and no loop; the same keystroke measured across three processes
takes 3.85 ms. **The difference is what an instruction count cannot see** — the
transport, and every moment nothing was running. Counting turns of the event
loop is the measurement for that half, and it is Lillecarl/pymux#232.

    nix build --file . checks.pymux-keystroke.run
    PYMUX_KEYSTROKE_INCLUDE=render nix build --file . checks.pymux-keystroke
    cp result/keystroke-budgets.txt pymux/tests/keystroke-budgets.txt

### What pymux costs a keystroke

Every check above says whether pymux draws the right cells. None of them says
whether it draws them soon enough, and for a multiplexer that is the quality the
whole argument is about. `checks.pymux-latency` is that number.

One keystroke gives three, and they add up. **input** is the key going into the
client's pty until the program in the pane reads it: the client, the socket and
the server's pipe input. **output** is the program writing until the frame
reaches the client's terminal: the parser, the screen, the renderer and the
diff. **round trip** is both, which is what a person sees when they hold a key
down. The program in the pane timestamps its own two moments into a file, so the
cut between the halves is exact rather than inferred.

The same program then runs on a **bare pty**, with nothing between it and the
master. Without that the number says nothing, because a millisecond belongs to
the machine that read it.

    bare  round trip     0.05 ms at the median
    pymux round trip     3.85 ms at the median, 7.6 at p99

    input                1.1 ms of it
    output               2.7 ms of it

**The gap is not what the fork costs.** A bare pty has no renderer, no diff and
no layout, so it is the fork *and* everything pymux draws — which is the honest
reading, and still the useful one: it is what a person gives up by running a
multiplexer at all.

Two things the first run said. **The output half is more than twice the input
half**, so the render path is where the time is and the keyboard path is not
worth tuning. And **the two transports are the same**: `PYMUX_ROUTE=integrated`
carries packets in queues instead of over a unix socket, and its median round
trip is inside the run-to-run noise of the socket's. The socket is not what
costs.

Not a gate, and nothing judges it: a wall clock belongs to the machine that read
it, and this runs in a sandbox beside other jobs. Read the distribution rather
than a mean — the tail is what a person notices.

    nix build --file . checks.pymux-latency.run
    PYMUX_LATENCY_SAMPLES=500 nix build --file . checks.pymux-latency.run
    PYMUX_ROUTE=integrated nix build --file . checks.pymux-latency.run

### How many turns of the event loop a keystroke costs

The gap between the two numbers above was 45% of a keystroke, and neither of
them could say what it was: an instruction count counts work, and waiting is
the absence of work. `checks.pymux-turns` is the number that can. It goes up
when pymux hands control back and waits, and the code decides it rather than
the machine.

It drives the program `checks.pymux-latency` drives, over a real
`ServerConnection`, on an event loop that counts `_run_once`. Each turn also
names the callbacks it ran, so a total that moved points at a hop.

**A keystroke is eight turns**, five hundred times out of five hundred on an
idle machine:

    the server reads the "in" packet            1
    the application takes the key, and writes
      it to the pane's pty                      1
    the pane answers, and the screen changes    1
    prompt_toolkit postpones the redraw         3
    the frame goes out as an "out" packet       1
    the client's reader takes it                1

Under sixteen processes of `yes` it is eight about six times in ten and eleven
the rest. A keystroke asks for a frame twice — the key press invalidates, and
the pane's answer invalidates. When the answer lands before the loop polls
again, one redraw carries both; when it misses that poll, the redraw of the key
press runs by itself and draws nothing, and the answer pays for a second one.

So the check holds the **shortest** keystroke of a run and judges nothing else:
load can only add the second redraw, never take a turn away.

    nix build --file . checks.pymux-turns.run
    PYMUX_TURNS_SAMPLES=1000 nix build --file . checks.pymux-turns.run
    PYMUX_TURNS_TRACE=3 nix build --file . checks.pymux-turns.run

### Where the time of a frame goes

`checks.pymux-profile` is the other half, and it is **not a gate and judges
nothing**: it samples the stack with pyinstrument while a real server draws for
a real client, so a person reading it sees which function the seconds are in. A
count says whether something got dearer; a profile says where.

Server and client are in one process, which is what `pymux integrated` is, so a
frame is followed the whole way instead of up to a socket. Three phases, because
"what a frame costs" is three questions: frames with nothing changed, frames
after a program printed a line, and frames after a key moved the focus.

    PYMUX_PROFILE_PANES=16 nix build --file . checks.pymux-profile.run
    less result/log
    $BROWSER result/idle.html

## Asking a running server what it is doing

Everything above measures a server that a check started. **A server a person
left running for a week is the one that goes wrong**, and until recently
nothing could ask it anything: the log said what it had done, and nothing said
what it was doing now.

py-spy is the usual answer and it often cannot be used. It needs `ptrace`, and
a machine with `kernel.yama.ptrace_scope` at 1 gives that only to an ancestor
of the target. So a pymux server answers for itself.

    pymux counters      # what it has done, and what asked for each frame
    pymux dump-stacks   # every thread, every task, and what each waits for
    pymux profile 5     # where its time goes, as text and as HTML

**`counters` is usually enough.** "Eleven frames a second" says a server is
busy; "eleven frames a second, and every one because an application asked" says
what is doing it, which is the whole diagnosis. The `Woke` reasons are what
carry it.

    --- what it has done, over 2d 4h 11m ---

                                       total per second
    frames out                        832104      11.03
    characters in them             418022913       5541

    what asked for a frame             total per second
    an application asked for a frame  831992      11.02
    a client reported its size            83       0.00

**`dump-stacks` adds the half a thread dump cannot show.** One thread runs the
event loop, so a thread dump of a server says "the loop is polling" and no
more. The work of a server is in its asyncio tasks, and this names each one and
the line it is waiting on.

**`profile` watches without stopping.** It returns at once and the server keeps
serving; the loop stops the profiler a few seconds later and writes the file.
It is pyinstrument with `async_mode="disabled"`, which is the mode that
interleaves every coroutine rather than following one context, and the tasks
are written beside it — so the profile says which code burned the processor and
the tasks say what everything else was waiting for.

### When the loop is too wedged to answer

A command needs a loop that still turns, and a wedged loop is exactly when a
stack is worth having. So a server also takes **`SIGUSR1`**, through
`faulthandler`, whose handler is C and runs when the interpreter is stuck
inside a call no Python code will return from.

    kill -USR1 $(pgrep -f 'pymux.*server')
    less ~/.local/state/pymux/stacks-<pid>.log

It gives less than `dump-stacks` and it gives it always. Everything lands
beside the log, because a dump is read with the log around it.

### Attaching a real debugger

Python 3.14 can attach one to a running process — `python -m pdb -p <pid>`,
and `sys.remote_exec` under it (PEP 768). That needs `ptrace` of the server,
which the machines above deny, and a server can say otherwise:

    pymux set-option allow-remote-debugging on

**Off by default, and it is not a small permission.** It lets any process
running as you read this server's memory and write to it, and a server holds
every pane's scrollback. The three commands above need none of it.

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
