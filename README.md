# pyterm

pymux and the stack it is built on, developed together:

| submodule | branch | upstream |
| --- | --- | --- |
| `pymux` | `graphics-protocol` | prompt-toolkit/pymux |
| `ptterm` | `graphics-protocol` | prompt-toolkit/ptterm |
| `pyte` | `graphics-protocol` | selectel/pyte |
| `prompt-toolkit` | `render-performance` | prompt-toolkit/python-prompt-toolkit |

Each package builds from its submodule working copy, so an edit in any of them
builds without a commit or a push.

## Building

    nix-build -A pymux          # or pyte, ptterm, prompt-toolkit
    nix-shell                   # pymux and umbrella on PATH

`default.nix` is the whole definition. `shell.nix` and `flake.nix` only call
into it, and the flake takes nixpkgs as its one input: everything else comes
from the submodules, except umbrella, which `default.nix` fetches from GitHub.

**A flake build needs the submodules asked for by name.** Flakes see only what
git tracks, and a submodule's contents are not that, so a plain `nix build .#`
fails with "Path 'prompt-toolkit' ... is not tracked by Git":

    nix build '.?submodules=1#pymux'

The `nix-build` path above has no such problem, and it reads the working copies
rather than the last commit, which is usually what you want while working.

## Driving the collection

    umbrella status             # what each submodule is doing
    umbrella land -p -m "..."   # push submodules, then record their pointers
    umbrella sync               # move submodules onto the recorded pointers
    umbrella wts add spike      # the whole collection again, sharing storage

`umbrella` refuses to record a submodule commit that no remote has, so a clone
can never land on a pointer nobody can fetch. Run `umbrella initjj` after
cloning to drive the submodules with jj, or `umbrella initgit` for plain git.
