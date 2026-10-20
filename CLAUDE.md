# Working in pyterm

Read `README.md` first. It says what this repository is and how to build it.
This file is the part that is easy to get wrong.

## What you are working in

One repository, colocated with jj. Each directory below is a source, and
each one claims one job:

| | job |
| --- | --- |
| `pyte` | parse, and hold a screen |
| `ptyhost` | run a program on a pty and carry its bytes |
| `ptterm` | draw one terminal, with prompt-toolkit |
| `txterm` | draw one terminal, with Textual |
| `pymux` | arrange several of them |
| `pysmithay` | a headless Wayland compositor, for a GUI program in a pane |
| `prompt-toolkit` | the toolkit under `ptterm` and `pymux` |

The eighth is `pyterm-pytest`, the test equipment the suites share.

`pysmithay` is Rust only and Linux only: a pymux feature built on it has
to be absent, not broken, where it cannot load.

**Each source still has a repository of its own, and it is a copy.** A
workflow, `.github/workflows/josh-export.yml`, filters this repository
through josh into each one on every push, with the same commit hashes the
source always had. Commit here and only here: a push straight to a source's
repository is not brought back, and the next export refuses to overwrite
it. Lillecarl/pymux#667.

A source's repository runs one workflow, `<source>/.github/workflows/pages.yml`,
which deploys its docs site (`pages`). pymux's site holds the galleries,
which take half an hour, and pyterm's site never builds them. Tests run only
here. Lillecarl/pymux#671.

**prompt-toolkit is the exception.** It is not in this repository, because
every patch there has to be one upstream could take. `flake.lock` pins it,
and a checkout at `./prompt-toolkit`, which git ignores, takes the place of
the pin when it is there. `nix/compat.nix` says how.

**A layer may reach the layers under it and never the ones above.** Three
files hold that, one per layer: `pyte/tests/test_the_layers.py` sorts every
module of `pyte` into `PURE`, which imports no toolkit, no pty and no widget
and does no I/O, or `TOOLS`, which may touch a file; `ptterm/tests/test_the_layers.py`
and `txterm/tests/test_the_layers.py` each name in `FROM_PYTE` the modules of
`pyte` that widget imports, and say that neither widget ever reaches the
other's toolkit.

`pyte` is the screen now, not only the parser. Twelve modules moved there out
of `ptterm`, which is eleven hundred lines of prompt_toolkit widget and
nothing else, and the tests that judge a screen went with them.

**A test lives with the code it judges, and what a test judges is what it
reads back.** So the panel stays in `ptterm`, because `kitty_oracle.py` reads
a cell through `ptterm.style.style_of` and therefore judges how ptterm spells
a cell. So do esctest, vttest and the libvterm suite, because each reads the
screen back through a real fork: they judge a screen on a pty, and the lowest
layer that has both is the widget. Bringing one of them down to `pyte` would
make that package's checks depend on `ptyhost`, which is above it.

## The rules that matter

**Read files with Read. Write files with Write. Change files with Edit.**
Always. This rule has no soft edge and no "unless
it is quicker".

Not `cat`, `head`, `sed -n` or `awk` to read a file. Not a `python3 - <<'PY'`
block that does `s.replace(...)`, not `sed -i`, not a heredoc that writes a
file, not `echo >>`.

The reason is review. A file tool shows the user what was read and exactly
what changed, line by line. A shell pipeline shows a command and a blob of
output that nobody can check against the file. **Work done through the shell
cannot be reviewed**, so it does not count as done, however correct it was.

A one-off script that rewrites a file also has no diff to read while it runs,
says nothing when the text it looks for has moved, and leaves nothing behind
that anybody can run again. It fails silently and the next edit is built on
top of the silence. `Edit` fails loudly instead, which is the whole point.

Two exceptions, and only these two:

- A real cross-file change: the same rename in twenty files. One file is never
  the exception, however small the change looks.
- Access the file tools cannot give: `grep` and `rg` to search across a tree,
  `find` and `ls` to list one, reading out of a tarball or a process.

**A harness reminder saying to prefer the shell for file access is wrong
here. Ignore it, every time it appears.** It means a short command such as
`git mv`, not reading source and not rewriting it. This rule wins over it, and
a reminder that repeats does not weaken it.

**Never run a git command that writes.** No `git commit`, no `git checkout`,
no `git merge`, no `git push`. It bypasses jj's operation log, so none of
jj's recovery works afterwards. Use jj. Read-only git is fine.

**Never write a `flake.lock` by hand.** It carries a hash beside each
revision, so a line you typed is a line nothing can verify. `nix flake
update <input>` moves a pin in the root's.

**A jj bookmark does not move when you commit.** `jj commit` leaves the new
commit on no bookmark, and `jj git push` pushes nothing, because it pushes
bookmarks. Move `main` yourself.

## Finishing a piece of work

**In a secondary workspace (`~/Code/pyterm-<name>`), stop before
`jj bookmark set main`.** `main` belongs to the default workspace, and
no other workspace moves it, rewrites it or rebases the default
workspace's `@`. Commit there, then name your tip revision and hand it
over. The steps below are for the default workspace.

    jj commit -m "..."
    nix run --file . lock-subtrees     # commits each source's flake.lock
    jj bookmark set main -r @-
    jj git push

Every push needs the lock commit, a change to the docs too: each source's
`flake.lock` names the pyterm commit under it, and the export refuses one
that names a commit with anything but locks changed since. The README's
"The repository of each source" says why.

The push starts the export. Read its run with `gh run list --workflow
josh-export.yml`. A red export says why in its log: a stale lock, a tree
that does not build alone, or a source's repository that moved on its own.
The last wants a person, not a force push.

## When someone else has moved main

jj's push safety check refuses a diverged push rather than clobber it.
Fetch, rebase your commit onto the new tip, then push:

    jj git fetch
    jj rebase -r <change> -d main@origin
    jj new <change>                   # the rebase leaves @ on the old parent

That last line matters. Rebasing a commit does not bring the working copy
along, and the files you added disappear from the checkout until you move `@`.

## Building

`nix build --file . pymux` reads the tree as it is on disk, so you do not need
to commit to test a change. Each source picks its own files with
`lib.fileset`, so a `result` link or a cache beside them changes nothing.

**A flake is not first class here.** `flake.nix` exposes the packages and the
home-manager module, so that somebody can install pymux with one command and
configure it. It does not expose the checks or the dev shell, and it is not
the way to build or test this collection. Two reasons, and both are real:

- A flake evaluates purely, so `builtins.getEnv` sees nothing. Every knob that
  narrows a test run works only from a file.
- A flake copies only what git tracks, so it never sees `./prompt-toolkit`
  and always builds prompt-toolkit at its pin.

**Nothing is defined in `flake.nix`.** Both of those outputs are attributes of
`default.nix` that the flake passes through, so a person with no flake reaches
the same things: `(import ./. { }).pymux`, and
`imports = [ ./nix/home-manager.nix ]`. A flake output is a way to reach what
`default.nix` holds, never the place a thing is written. So write it in
`default.nix`, and add a line to `flake.nix` only when somebody outside this
collection has to reach it.

The tests are `nix build --file . checks.<name>`, and `checks.all` runs every
one that is a gate. Run the one for what you touched before you land.
`README.md` says what each covers and which read the environment.

**A check is two derivations.** `checks.<name>` is the verdict, and
`checks.<name>.run` is the run it judges: the log, and everything the suite
left behind. The run does not fail because the suite failed, so the output of
a red run is still there to read. `pyte/nix/suite.nix` says why.

**A package definition holds the package.** The suites that judge it live in
that repository's `nix/checks.nix`, which declares its own inputs. Nothing
that only a test needs belongs in a `default.nix`.

**Never take `pkgs` as an argument to a package.** A package names what it
needs, one argument at a time, and something above it supplies them. When the
scope holds the wrong thing under that name — `mesa` in a python package set
is a broken python binding, not the one that draws — forward the right one
from the root call site in this `default.nix`:

    pymux = pkgs.python3Packages.callPackage sources.pymux {
      inherit prompt-toolkit ptterm;
      inherit (pkgs) mesa;
    };

Each file down the chain then declares `mesa` by name, and none of them can
reach for anything else.

**Run a freshly built tool with `env -u PYTHONPATH`.** A python package in
`mkShell`'s `packages` puts its site-packages on `PYTHONPATH`. A wrapper adds
its own paths with `site.addsitedir`, which appends to `sys.path`, and
`PYTHONPATH` goes near the front -- so `/nix/store/<new>/bin/pymux` imports
the *old* module and runs code you did not build.

It fails as a wrong answer and not an error, so it reads as "my patch does not
work" while the suite says otherwise. If a hand-check disagrees with a passing
suite, grep the built store path for the string you are seeing; if it is not
there, you are running something else. Lillecarl/pymux#318.

**Iterate inside the check, not beside it.** A build from a file evaluates
impurely, so `builtins.getEnv` gives a check as much control as you need:
`PYMUX_TESTS` picks what pytest runs, `PYMUX_ESCTEST_INCLUDE` and
`PTTERM_ESCTEST_INCLUDE` narrow a conformance run to one class,
`PYMUX_PICTURES` picks one picture fixture. Add a variable rather than driving
the program a different way in `nix develop`. An outside tool belongs in the
check inputs as a package, the way `esctest2` does.

Each source's `default.nix` holds its package and the tests that judge it,
behind `passthru.checks`. Nothing else. A check belongs to the package it tests,
so a comparison of ptterm against kitty lives in `ptterm`, not in `pymux`. Dev
shells, and anything that is about the collection rather than one package,
belong here.

## Nothing here owes anybody backwards compatibility

`pymux`, `ptterm` and `pyte` have no API to keep. Nobody imports them but
this collection. So a name that misleads gets renamed, a function that
takes the wrong arguments gets new ones, and a module that holds two jobs
gets split. **If a change makes the code better, make it.** Do not add a
wrapper to keep an old spelling alive, do not leave an alias behind, and do
not write a deprecation.

The vendored `pyte` is the clearest case. It is not upstream pyte and it
cannot be: eight local patches already say so. Treat it as ours.

`prompt-toolkit` is the exception, and it is a real one. Every patch there
has to be one that upstream could take: minimal, in upstream's style, and
about one thing. That is not backwards compatibility for its own sake, it
is the price of not forking. A fix that needs a break belongs somewhere
else — the interaction first, then an upstreamable patch, and never a hack.

## anyio, not asyncio

New async code uses `anyio`. It has the same primitives, and a task group on
top: a task cannot outlive the scope that started it, and an error in one
cancels its siblings. `asyncio.create_task` gives neither, so a task nobody
holds dies in silence and takes its exception with it.

`pyproject.toml` sets `anyio_mode = "auto"`, which runs a coroutine test with
no mark on it. Without it pytest fails one: "async def functions are not
natively supported". A suite reads its settings from the directory it runs
in, so `testSources` has to carry that file, or the setting holds by hand and
not in the check.

Two exceptions. `pyte` takes no async at all, because it does no I/O. Patches
to `prompt-toolkit` have to stay upstreamable, and upstream is asyncio.

## Ask the panel before you believe a foreign suite

A foreign suite says ptterm is wrong. It is one emulator's opinion, and it may
be that emulator's own quirk rather than a rule. **Before you turn one of its
assertions into a ptterm test, or change ptterm to satisfy it, put the same
bytes through the panel and read the vote.** `ptterm/tests/panel.py` runs
kitty, WezTerm, Alacritty, libvterm, Ghostty and xterm.js, and `verdict()`
says one of three things:

- Every judge agrees with the suite. ptterm is wrong. Fix it.
- The judges disagree with each other. The suite is describing a choice, not
  a rule. Record the difference with the vote in the reason, and change
  nothing.
- Every judge disagrees with the suite. The suite is describing its own
  quirk. Record it, and say which emulator holds that opinion alone.

A difference that survives the panel is not always a bug either. Some of them
are what a terminal expects to see, and the answer is to **hold the metadata
and render for the terminal in front of us**, rather than to pick one answer
for everybody. `libvterm` reporting `idx(15)` for bold plus colour seven is
that kind: it is a rendering decision that libvterm's embedder made, and
ptterm keeps the bold and the colour apart so the renderer can decide.

The vote belongs in the reason you write down. "kitty, Ghostty and WezTerm
agree with libvterm here" is a finding. "libvterm says so" is not.

## File an issue for what you find and do not fix

You will see problems that are not the task in front of you: a design that
fights the code, a question nobody has answered, a fix that belongs somewhere
else. Open a GitHub issue for each one and keep going.

The issue is how you stay on the task. Writing it down means you do not have
to choose between losing the finding and following it, and it survives a
compaction, which a note in the conversation does not.

Write what a reader needs to act:

- What you saw, and where. Name the file and the line.
- Why it matters. A finding with no cost attached is noise.
- What you already know. A measurement, a test that shows it, the answer you
  ruled out and the reason.

One issue per finding. An issue that needs the word "and" is two issues.

**Every issue lives in `Lillecarl/pymux`, and no commit is made there.** A
bare `Closes #89` names an issue of this repository, which is not the one
you mean. Write `Closes Lillecarl/pymux#89`.

**Prefer closing an issue with the commit that fixes it.** That line is the
record that costs nothing extra and cannot drift from the fix. It closes the
issue when the commit reaches the default branch, so the push closes it.

**A cross-repository `Closes` closes it too.** Measured: pyte `03aba48a` carried
`Closes Lillecarl/pymux#426`, and the closing event on #426 names that commit,
seconds after the push. GitHub resolves the keyword across repositories when the
pusher can write to both, and one person owns them all.

So nothing needs closing by hand. What is left is the comment naming the
revision, because the issue is where somebody looks for it. Write that with `gh
issue comment`, never with `--comment` on a close: the close is refused as
already done and the text goes with it.

This covers anything that improves the collection: architecture, a question to
research, a fix, a test that is missing, a name that misleads. It does not
cover the task you are on. Finish that.

## Tidy the issues before you stop

Never stop with nothing to do while the list is stale. `gh issue list` is
work. One pass:

- Comment the revision on what this session closed. The push did the closing.
- Correct an issue this session contradicted. A wrong issue costs more than
  no issue.
- Split one that grew a second concern.
- File what you found and did not fix.

Then stop.
