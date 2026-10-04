# The collection

Eight repositories; `umbrella status` shows all eight at once. Each
has one job:

| repo | job |
| --- | --- |
| `pyte` | parse input, hold the screen |
| `ptyhost` | run a program on a pty, carry its bytes |
| `ptterm` | draw one terminal (prompt-toolkit) |
| `txterm` | draw one terminal (Textual) |
| `pymux` | arrange several terminals |
| `pyterm-pytest` | test equipment the suites share |
| `prompt-toolkit` | upstream toolkit under `ptterm`/`pymux` |
| `umbrella` | source control: pins revisions, lands, marks |

`umbrella` is plumbing, not product. Touch it only when asked, or
for a bug found there. Same for its lock file: `umbrella land`
writes `nix/sources.lock`, never a hand.

`prompt-toolkit` is upstream, not ours. Hands off, except a patch
upstream could take: minimal, in upstream style, about one thing
(`prompt-toolkit-upstreaming.md`).

The other six are ours. Maintain them to collection standards:
`ruff.toml` (15 rules, width 120, lazy annotations, floor 3.14),
one `checks.*-ruff` gate per package, tests beside the code they
judge, no backwards compatibility. `CLAUDE.md` holds the rest.
