# Upstream-ready checklist (prompt-toolkit)

A PR to `prompt-toolkit/python-prompt-toolkit` is ready when every box
holds. Run what is runnable; the rest is judgment, done by hand.

## Shape

- [ ] One concern per commit; change and test ride together. A fixup
      of its own parent is squashed, not stacked.
- [ ] No unrelated reformats, no drive-by fixes, no foreign tracker
      references in code or messages.
- [ ] Provenance rule applied the same everywhere (trailers kept on
      every commit, or disclosure in the PR body instead).
- [ ] Branch is N commits on the current upstream release, nothing
      else: `jj diff --from <release> --to <branch> --stat`.

## Messages

- [ ] Subject short and descriptive, in upstream's voice.
- [ ] Body says why, states the equivalence invariant for refactors,
      and names the edge cases (empty, single, no-growth, ...).
- [ ] Numbers carry a method anyone can redo (what, how many runs,
      which interpreter). No foreign harnesses, no uncountables.

## Proof

- [ ] `prompt-toolkit-ci` green on the branch (pytest, ruff check,
      ruff format, typos, mypy loop). Pre-existing failures recorded,
      not fixed here and not hidden.
- [ ] `prompt-toolkit-pyrefly` clean on the changed files.
- [ ] Every behavior change pinned by a test that fails without it
      (mutation-tested or reverted, not assumed) -- or recorded as
      pinning rather than discriminating, with the reason.
- [ ] Full suite green on the branch tip, not only the new tests.

## Compatibility

- [ ] Public names and signatures unchanged; a widened annotation
      stays backward compatible.
- [ ] Docstrings still true after the change; comments carry
      mechanism, not measurements and no pointers elsewhere.
- [ ] The `requires-python` floor holds: no syntax or stdlib newer
      than it allows.

## Submission

- [ ] Rebased onto current upstream HEAD; upstream has not moved
      since (`git ls-remote <upstream> HEAD`).
- [ ] PR body: what, why, measurements, tests, disclosure line.
