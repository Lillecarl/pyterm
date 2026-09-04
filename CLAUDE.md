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
commit to test a change. A flake build needs `nix build '.?submodules=1#pymux'`,
because flakes see only what git tracks and submodule contents are not that.

The tests are `nix build --file . checks.<name>`: `pyte`, `ptterm`, `pymux`,
`pymux-pty`, `pymux-esctest` and `ptterm-fuzz`. Run the one for what you
touched before you land. `README.md` says what each covers and which read the
environment.

**Iterate inside the check, not beside it.** A build from a file evaluates
impurely, so `builtins.getEnv` gives a check as much control as you need:
`PYMUX_TESTS` picks what pytest runs, `PYMUX_ESCTEST_INCLUDE` narrows the
conformance run to one class, `PYMUX_ESCTEST_RECORD` makes it write its list
instead of judging one. Add a variable rather than driving the program a
different way in `nix develop`. An outside tool belongs in the check inputs as
a package, the way `esctest2` does.

Each submodule's `default.nix` holds its package and the tests that judge it,
behind `passthru.checks`. Nothing else. A check belongs to the package it tests,
so a comparison of ptterm against kitty lives in `ptterm`, not in `pymux`. Dev
shells, and anything that is about the collection rather than one package,
belong here.

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

This covers anything that improves the collection: architecture, a question to
research, a fix, a test that is missing, a name that misleads. It does not
cover the task you are on. Finish that.
