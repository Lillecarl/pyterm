# Working in pyterm

Read `README.md` first. It says what this repository is and how to build it.
This file is the part that is easy to get wrong.

## What you are working in

Five submodules, each a git repository colocated with jj, held together by an
umbrella that records one commit per submodule. Four of them are the code:
`pymux`, `ptterm`, `pyte` and `prompt-toolkit`. The fifth is `umbrella` itself,
the tool that holds the other four together. `umbrella status` tells you the
state of all five at once. Run it before you start and after you finish.

The mode is jj. Every submodule has a `.jj` directory, and jj owns them.

## The rules that matter

**Read files with Read. Write files with Write. Change files with Edit.**
Always. Here and in every submodule. This rule has no soft edge and no "unless
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

**Never run a git command that writes inside a submodule.** No `git commit`, no
`git checkout`, no `git merge`, no `git push`. It bypasses jj's operation log,
so none of jj's recovery works afterwards. Use jj: `jj -R <submodule> commit`,
`jj -R <submodule> new`, and so on. Read-only git is fine.

**Never record a submodule pointer by hand.** `git add <submodule>` followed by
`git commit` is how a collection ends up naming a commit that no remote has, and
then every clone breaks. Use `umbrella land`. The hooks refuse the manual route
anyway, and the refusal is telling you something real.

**Land, do not push.** `umbrella land -p -m "..."` moves each submodule's
bookmark onto the commit being published, pushes it, records the pointer here,
commits, and pushes this repository. In that order. Doing it by hand means doing
those five things in that order without forgetting the bookmark, which is the
step everyone forgets.

**A jj bookmark does not move when you commit.** This is the reason `land`
exists. `jj commit` leaves the new commit on no bookmark, git HEAD points at it,
and `jj git push` pushes nothing, because it pushes bookmarks. `land` moves the
bookmark for you, fast forward only, and says which one it moved.

## Finishing a piece of work

    jj -R pymux commit -m "..."      # or just describe @; land closes it
    umbrella status                  # confirm what you expect to land
    umbrella land -p -m "..."

`land` also accepts work left in the working commit: if `@` has changes and a
description, it closes it for you. If `@` has changes and no description, it
leaves it alone and says so, because jj itself refuses to push an undescribed
commit.

## When someone else has moved a branch

`umbrella status --fetch` reports `origin/<branch>-moved-ahead`. jj's push safety
check will refuse a diverged push rather than clobber it. Fetch, rebase your
commit onto the new tip, then land:

    jj -R <submodule> git fetch
    jj -R <submodule> rebase -r <change> -d <branch>@origin
    jj -R <submodule> new <branch>     # the rebase leaves @ on the old parent

That last line matters. Rebasing a commit does not bring the working copy along,
and the files you added will disappear from the checkout until you move `@`.

## Worktrees

Ask for a worktree and you get the whole collection again, as jj workspaces
sharing storage rather than four clones. `.claude/settings.json` points the
worktree hooks at umbrella and turns the `jj-worktrees` plugin off for this
project, because hooks merge across settings files and two of them would each
build a worktree.

A worktreespace does not publish. `land` refuses there, and `status` says what
it is rather than pretending to know about pointers. Land from the checkout it
came from.

## If a hook says umbrella is not on PATH

`.claude/settings.json` calls `umbrella` by name, so it has to be on the PATH
Claude itself was started with. `.envrc` puts it there, but only for shells
direnv has exported into. Start Claude from a shell where `direnv` has run, or
pin an absolute path for this checkout alone:

    umbrella initcc --local --command "$(command -v umbrella)"

That writes `.claude/settings.local.json`, which is local and not committed.

## Building

`nix build --file . pymux` reads the working copies, so you do not need to
commit to test a change.

**A flake is not first class here.** `flake.nix` exposes the packages and
nothing else, so that somebody can install pymux with one command. It does not
expose the checks or the dev shell, and it is not the way to build or test
this collection. Two reasons, and both are real:

- A flake evaluates purely, so `builtins.getEnv` sees nothing. Every knob that
  narrows a test run works only from a file.
- A flake sees only what git tracks, and the contents of a submodule are not
  that, so even a package build needs `nix build '.?submodules=1#pymux'`.

Do not add outputs to `flake.nix` to make something reachable. Add it to
`default.nix`, where everything already is.

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

    pymux = pkgs.python3Packages.callPackage ./pymux {
      inherit prompt-toolkit ptterm;
      inherit (pkgs) mesa;
    };

Each file down the chain then declares `mesa` by name, and none of them can
reach for anything else.

**Iterate inside the check, not beside it.** A build from a file evaluates
impurely, so `builtins.getEnv` gives a check as much control as you need:
`PYMUX_TESTS` picks what pytest runs, `PYMUX_ESCTEST_INCLUDE` and
`PTTERM_ESCTEST_INCLUDE` narrow a conformance run to one class,
`PYMUX_PICTURES` picks one picture fixture. Add a variable rather than driving
the program a different way in `nix develop`. An outside tool belongs in the
check inputs as a package, the way `esctest2` does.

Each submodule's `default.nix` holds its package and the tests that judge it,
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

**Every issue lives in `Lillecarl/pymux`, and most commits do not.** A bare
`Closes #89` in a ptterm or pyte commit names an issue of that repository, which
is not the one you mean. Write `Closes Lillecarl/pymux#89`, and close the issue
by hand with a comment that says what closed it.

This covers anything that improves the collection: architecture, a question to
research, a fix, a test that is missing, a name that misleads. It does not
cover the task you are on. Finish that.

## Tidy the issues before you stop

Never stop with nothing to do while the list is stale. `gh issue list` is
work. One pass:

- Close what this session closed, and say in the comment what closed it.
- Correct an issue this session contradicted. A wrong issue costs more than
  no issue.
- Split one that grew a second concern.
- File what you found and did not fix.

Then stop.
