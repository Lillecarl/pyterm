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
`ruff.toml` (143 rules, width 120, lazy annotations, floor 3.14),
one `checks.*-ruff` gate per package, tests beside the code they
judge, no backwards compatibility. `CLAUDE.md` holds the rest.

A change that touches frame cost is profiled on a huge screen too
(856x178), not only at the issue's geometry: copy, diff and wire
grow with damage and size, and a small screen hides all three.
`PYMUX_PROFILE_ROWS/COLUMNS` size `checks.pymux-profile.run`;
`PYMUX_PROFILE_PHASES` narrows it. Wall-clock moves with box load,
so report the load beside the number and compare structure
(self-time ranking), not just milliseconds.
