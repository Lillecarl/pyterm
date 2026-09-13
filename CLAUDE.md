# Working in pyterm

Read `README.md` first. It says what this repository is and how to build it.
This file is the part that is easy to get wrong.

## What you are working in

Eight repositories, each colocated with jj, held together by an umbrella that
locks one revision per source in `nix/sources.lock`. Six of them are the code,
and each one claims one job:

| | job |
| --- | --- |
| `pyte` | parse, and hold a screen |
| `ptyhost` | run a program on a pty and carry its bytes |
| `ptterm` | draw one terminal, with prompt-toolkit |
| `txterm` | draw one terminal, with Textual |
| `pymux` | arrange several of them |
| `prompt-toolkit` | the toolkit under `ptterm` and `pymux` |

The seventh is `pyterm-pytest`, the test equipment the suites share. The
eighth is `umbrella` itself, the tool that holds the others together.
`umbrella status` tells you the state of all eight at once. Run it before you
start and after you finish.

**They are not submodules.** They were until 2026-09-13. Now `nix/sources.nix`
says where each comes from and `nix/sources.lock` says which revision, and the
working copies are ordinary clones that this repository ignores -- nothing
about them is committed here. `umbrella fetch` makes one that is missing.

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

The mode is jj, and this repository is a jj repo too, colocated like the
sources. It could not be while the sources were submodules: jj ignores
gitlinks, so a jj working copy here would have dropped every pointer. With
the pointers gone there is nothing left for it to drop -- jj tracks the
umbrella's own two dozen files and ignores the eight checkouts, which
`.git/info/exclude` lists.

## The rules that matter

**Read files with Read. Write files with Write. Change files with Edit.**
Always. Here and in every source. This rule has no soft edge and no "unless
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

**Never run a git command that writes inside a source.** No `git commit`, no
`git checkout`, no `git merge`, no `git push`. It bypasses jj's operation log,
so none of jj's recovery works afterwards. Use jj: `jj -R <source> commit`,
`jj -R <source> new`, and so on. Read-only git is fine.

**Never write `nix/sources.lock` by hand.** It carries a `narHash` beside each
revision, so a line you typed is a line nothing can verify. `umbrella land`
writes it, and only for revisions it has just pushed -- which is the whole
point: a lock naming a commit no remote has breaks every clone.

**Land, then commit the lock.** `umbrella land` moves each source's bookmark
onto the commit being published, pushes it, and writes the lock. It stops
there, on purpose: it will not guess which commands you want for the umbrella
itself. So landing is two steps, and the second one is yours -- and the
bookmark trap applies again, because this repository is jj as well.

**A jj bookmark does not move when you commit.** This is the reason `land`
exists. `jj commit` leaves the new commit on no bookmark, git HEAD points at
it, and `jj git push` pushes nothing, because it pushes bookmarks. `land`
moves the bookmark for you, fast forward only, and says which one it moved.

## Finishing a piece of work

    jj -R pymux commit -m "..."      # or just describe @; land closes it
    umbrella status                  # confirm what you expect to land
    umbrella land                    # bookmark, push, write nix/sources.lock
    jj commit -m "..."               # this repository's own commit
    jj bookmark set main -r @-       # land moves a source's bookmark, not this one
    jj git push

`land` also accepts work left in the working commit: if `@` has changes and a
description, it closes it for you. If `@` has changes and no description, it
leaves it alone and says so, because jj itself refuses to push an undescribed
commit.

There is no `--dry-run` on `land`. The push is what makes a revision public
and nothing takes it back, so a flag that pushed and then claimed to have
changed nothing would lie about the only step that matters.

## When someone else has moved a branch

`umbrella status --fetch` reports `origin/<branch>-moved-ahead`. jj's push safety
check will refuse a diverged push rather than clobber it. Fetch, rebase your
commit onto the new tip, then land:

    jj -R <source> git fetch
    jj -R <source> rebase -r <change> -d <branch>@origin
    jj -R <source> new <branch>        # the rebase leaves @ on the old parent

That last line matters. Rebasing a commit does not bring the working copy along,
and the files you added will disappear from the checkout until you move `@`.

## Worktrees

**`umbrella wts` does not work here any more, and asking for a worktree
fails.** Colocating this repository with jj is what stopped it:

    umbrella: this umbrella is a jj repo, and a worktreespace of one cannot
    hold the markers umbrella needs. Use jj workspace add.

**It is a fixable limitation, not a rule.** `wts` writes three markers -- the
worktreespace name, the mode, the kind -- into `Path(repo.path)`, which is the
`.git` directory, and a jj workspace has no `.git` of its own. `Umbrella.open`
then calls `pygit2.discover_repository`, which finds nothing:

    $ jj workspace add --name probe /tmp/probe && cd /tmp/probe
    $ ls -a .jj ; ls -a .git
    repo  working_copy      ls: .git: No such file or directory
    $ umbrella status
    umbrella: not inside a git repo.

A workspace does have `.jj/`, which is per workspace and never committed, and
`.jj/repo` points at the real repository. So both halves have a home: the
markers go in `.jj/` when there is one, and `open` reaches the git repo
through `.jj/repo/store/git_target`. Lillecarl/pymux#316 holds the patch.

Until it is written, `.claude/settings.json` still points `WorktreeCreate` at
`umbrella hook worktree-create`, so asking for a worktree runs a hook that
errors. Work in the checkout.

## If a hook says umbrella is not on PATH

`.claude/settings.json` calls `umbrella` by name, so it has to be on the PATH
Claude itself was started with. `.envrc` puts it there, but only for shells
direnv has exported into. Start Claude from a shell where `direnv` has run, or
pin an absolute path for this checkout alone:

    umbrella initcc --local --command "$(command -v umbrella)"

That writes `.claude/settings.local.json`, which is local and not committed.

## Building

`nix build --file . pymux` reads the working copies, so you do not need to
commit to test a change. **That is `UMBRELLA_DEV=all`, and `.envrc` sets it.**
Without it a build takes each source at the revision the lock names, which is
the committed tree: an edit you have not committed does not reach it. Measured
-- a `git+file://` fetch pinned to a revision gives the same store path with a
tracked file modified as without. `nix/resolve.nix` holds both arms. CI leaves
the variable unset and gets the reproducible one.

**A flake is not first class here.** `flake.nix` exposes the packages and the
home-manager module, so that somebody can install pymux with one command and
configure it. It does not expose the checks or the dev shell, and it is not
the way to build or test this collection. Two reasons, and both are real:

- A flake evaluates purely, so `builtins.getEnv` sees nothing. Every knob that
  narrows a test run works only from a file.
- A flake evaluates purely, so it never reads a working copy: it resolves
  every source through `nix/sources.lock` and builds what was last landed,
  not what is on your disk.

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
