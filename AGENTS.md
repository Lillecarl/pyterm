# The collection

One repository. Each directory is a source with one job, and josh
exports each to a repository of its own (`pkgs/josh-export`), which
builds alone through its own `flake.lock` (`pkgs/lock-subtrees`):

| directory | job |
| --- | --- |
| `pyte` | parse input, hold the screen |
| `ptyhost` | run a program on a pty, carry its bytes |
| `ptterm` | draw one terminal (prompt-toolkit) |
| `txterm` | draw one terminal (Textual) |
| `pymux` | arrange several terminals |
| `pysmithay` | headless Wayland compositor (Rust, Linux) |
| `pyterm-pytest` | test equipment the suites share |
| `prompt-toolkit` | upstream toolkit under `ptterm`/`pymux` |

`prompt-toolkit` is upstream, not ours, and not in this repository:
`flake.lock` pins it, and an ignored checkout at
`./prompt-toolkit` replaces the pin. Hands off, except a patch
upstream could take: minimal, in upstream style, about one thing
(`prompt-toolkit-upstreaming.md`). `nix flake update prompt-toolkit`
moves the pin, never a hand.

The other seven are ours. Maintain them to collection standards:
`ruff.toml` (143 rules, width 120, lazy annotations, floor 3.14),
one `checks.*-ruff` gate per package, tests beside the code they
judge, no backwards compatibility. `CLAUDE.md` holds the rest.
Shared files (ruff stanza, README head/tail, `default.nix`,
`shell.nix`, `nix/compat.nix`, `.gitignore`, `pages.yml`) are copies:
edit the root's (`ruff.toml`, `nix/shared/`), then
`nix run --file . sync-sources`; `checks.pyterm-sources-in-step`
gates drift.

A change that touches frame cost is profiled on a huge screen too
(856x178), not only at the issue's geometry: copy, diff and wire
grow with damage and size, and a small screen hides all three.
`PYMUX_PROFILE_ROWS/COLUMNS` size `checks.pymux-profile.run`;
`PYMUX_PROFILE_PHASES` narrows it. Wall-clock moves with box load,
so report the load beside the number and compare structure
(self-time ranking), not just milliseconds.
