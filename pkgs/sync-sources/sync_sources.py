"""
Copy what every source shares out of pyterm's root, or check the copies.

A source's checks run in a sandbox that sees only its own tree, and its
repository stands alone, so it cannot read a file of the root. Each one
holds a copy instead:

- `ruff.toml`, everything above `[lint.isort]`, as the `[tool.ruff]` and
  `[tool.ruff.lint]` of its `pyproject.toml`. The copy ends at the
  source's own `[tool.ruff.lint.isort]`, which names its first-party
  modules and is kept by hand.
- `nix/shared/gitignore`, as its `.gitignore`.
- `nix/shared/readme-head.md` and `readme-tail.md`, with the source's
  name in them, as the start and the end of its `README.md`. The first
  and last line of each is a comment, which is how the copy is found
  again; what lies between the two is the source's own.

    sync-sources [ROOT]            rewrite each copy
    sync-sources --check [ROOT]    exit 1 if a copy differs

A source is a top-level directory with a `flake.nix` and a
`pyproject.toml`, except the ignored prompt-toolkit checkout: upstream's
files are not these.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Final

MARK: Final = "# Copied from pyterm's `ruff.toml`"
GENERATED: Final = f"{MARK} by `sync-sources`. Change it there.\n"
OWN: Final = "[tool.ruff.lint.isort]\n"
SHARED: Final = {"nix/shared/gitignore": ".gitignore"}


def stanza(ruff_toml: str) -> str:
    shared, isort, _ = ruff_toml.partition("\n[lint.isort]\n")
    if not isort:
        raise SystemExit("ruff.toml: no [lint.isort] to end the shared part at")
    head, lint, rules = shared.partition("\n[lint]\n")
    if not lint:
        raise SystemExit("ruff.toml: no [lint]")
    return f"{GENERATED}[tool.ruff]\n{head.rstrip()}\n\n[tool.ruff.lint]\n{rules.rstrip()}\n\n"


def with_stanza(pyproject: str, copy: str, name: str) -> str:
    start = pyproject.find(MARK)
    if start < 0:
        start = pyproject.find("[tool.ruff]\n")
    end = pyproject.find(OWN)
    if start < 0 or end < start:
        raise SystemExit(f"{name}/pyproject.toml: needs [tool.ruff] followed by {OWN.strip()}")
    return pyproject[:start] + copy + pyproject[end:]


def with_frame(readme: str, head: str, tail: str, name: str) -> str:
    head_end = head.rstrip("\n").rsplit("\n", 1)[-1]
    tail_start = tail.split("\n", 1)[0]
    _, found_head, body = readme.partition(head_end + "\n")
    body, found_tail, _ = body.partition(tail_start)
    if not found_head or not found_tail:
        raise SystemExit(f"{name}/README.md: needs the lines {head_end!r} and {tail_start!r}")
    return head + "\n" + body.strip("\n") + "\n\n" + tail


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("root", nargs="?", default=".", type=Path)
    parser.add_argument("--check", action="store_true", help="change nothing; exit 1 if a copy differs")
    args = parser.parse_args()

    copy = stanza((args.root / "ruff.toml").read_text())
    shared = {to: (args.root / origin).read_text() for origin, to in SHARED.items()}
    head = (args.root / "nix/shared/readme-head.md").read_text()
    tail = (args.root / "nix/shared/readme-tail.md").read_text()
    stale = []
    for flake in sorted(args.root.glob("*/flake.nix")):
        source = flake.parent
        name = source.name
        pyproject = source / "pyproject.toml"
        if not pyproject.exists() or name == "prompt-toolkit":
            continue
        wanted = {pyproject: with_stanza(pyproject.read_text(), copy, name)}
        wanted |= {source / to: text for to, text in shared.items()}
        readme = source / "README.md"
        wanted[readme] = with_frame(
            readme.read_text(), head.replace("{name}", name), tail.replace("{name}", name), name
        )
        for path, after in wanted.items():
            before = path.read_text() if path.exists() else None
            if before == after:
                continue
            stale.append(path)
            if args.check:
                print(f"{path.relative_to(args.root)}: differs from the root's")
            else:
                path.write_text(after)
                print(f"{path.relative_to(args.root)}: rewritten")
        print(f"{name}: checked")
    if args.check and stale:
        print("run `nix run --file . sync-sources` and commit", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
