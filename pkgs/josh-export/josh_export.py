"""
Export each source of pyterm to its own repository, through josh.

The workflow `josh-export.yml` runs it, and so can a person, from a
checkout with the whole history. Lillecarl/pymux#667.

    josh-export REV            report what an export of REV would do
    josh-export REV --verify   and evaluate each exported tree on its own
    josh-export REV --push     and push it

Per source: filter REV through `:/<source>`, which gives the source's own
commits back with their own hashes. Refuse unless the source's `main` exists
and is an ancestor of the export, and the target branch is absent or one
too: the push is never forced, and nothing here rewrites what a repository
already holds.

`--verify` evaluates each exported tree as a flake, with pyterm taken from
this repository at the commit the tree's lock names, and requires the
derivation pyterm builds for that source here. Lillecarl/pymux#670.

JOSH_REMOTE is the URL of a source with {} for its name, and JOSH_BRANCH
the branch to push to, `main` unless named.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tarfile
import tempfile
from io import BytesIO
from pathlib import Path
from typing import Final

DEFAULT_REMOTE: Final = "git@github.com:Lillecarl/{}.git"
MAIN: Final = "main"
# Not under refs/heads, so jj does not take an export for a bookmark.
REF_PREFIX: Final = "refs/josh-export/"


def run(*args: str, cwd: Path | None = None) -> str:
    return subprocess.run(args, cwd=cwd, check=True, capture_output=True, text=True).stdout.strip()


def sources(root: Path) -> list[str]:
    """A source is a top-level directory with a tracked `flake.nix`."""
    tracked = run("git", "-C", str(root), "ls-files", "--", "*/flake.nix").splitlines()
    return sorted(path.split("/")[0] for path in tracked if path.count("/") == 1)


def remote_head(url: str, branch: str) -> str | None:
    out = run("git", "ls-remote", url, f"refs/heads/{branch}")
    return out.split()[0] if out else None


def holds_ancestor(root: Path, ancestor: str, descendant: str) -> bool:
    """Whether this repository holds `ancestor`, and it is one of `descendant`."""
    known = subprocess.run(["git", "-C", str(root), "cat-file", "-e", f"{ancestor}^{{commit}}"], capture_output=True)
    if known.returncode != 0:
        return False
    return subprocess.run(["git", "-C", str(root), "merge-base", "--is-ancestor", ancestor, descendant]).returncode == 0


def verify(root: Path, name: str, exported: str, system: str) -> str | None:
    """The reason the exported tree does not stand on its own, or None."""
    with tempfile.TemporaryDirectory() as tmp:
        tree = Path(tmp) / name
        archive = subprocess.run(["git", "-C", str(root), "archive", exported], check=True, capture_output=True).stdout
        with tarfile.open(fileobj=BytesIO(archive)) as tar:
            tar.extractall(tree, filter="data")
        lock = json.loads((tree / "flake.lock").read_text())
        rev = lock["nodes"]["pyterm"]["locked"]["rev"]
        standalone = run(
            "nix",
            "eval",
            "--raw",
            f"path:{tree}#packages.{system}.default.drvPath",
            "--override-input",
            "pyterm",
            f"git+file://{root}?rev={rev}",
        )
    here = run("nix", "eval", "--raw", "--file", str(root), f"{name}.drvPath")
    if standalone != here:
        return f"builds {standalone} on its own, and {here} in pyterm"
    return None


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("rev")
    parser.add_argument("--verify", action="store_true", help="evaluate each exported tree on its own")
    parser.add_argument("--push", action="store_true", help="push each export, never forced")
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument("--system", default=run("nix", "eval", "--impure", "--raw", "--expr", "builtins.currentSystem"))
    args = parser.parse_args()

    root = Path(run("git", "-C", str(args.root), "rev-parse", "--show-toplevel"))
    remote = os.environ.get("JOSH_REMOTE", DEFAULT_REMOTE)
    target = os.environ.get("JOSH_BRANCH", MAIN)
    commit = run("git", "-C", str(root), "rev-parse", f"{args.rev}^{{commit}}")
    print(f"exporting {commit} to the {target} branches")

    failed = False
    for name in sources(root):
        url = remote.format(name)
        ref = REF_PREFIX + name
        run("josh-filter", f":/{name}", commit, "--update", ref, cwd=root)
        exported = run("git", "-C", str(root), "rev-parse", ref)
        main_head = remote_head(url, MAIN)
        target_head = remote_head(url, target)
        if main_head is None:
            verdict = f"REFUSED: no {MAIN}"
        elif not holds_ancestor(root, main_head, exported):
            verdict = f"REFUSED: {MAIN} is not behind the export; it moved on its own"
        elif target_head is not None and not holds_ancestor(root, target_head, exported):
            verdict = f"REFUSED: {target} is not behind the export"
        elif args.verify and (reason := verify(root, name, exported, args.system)):
            verdict = f"REFUSED: {reason}"
        else:
            verdict = "ok"
        print(
            f"{name}: export {exported[:12]}, {MAIN} {(main_head or '')[:12]}, {target} {(target_head or '')[:12]}: {verdict}"
        )
        if verdict != "ok":
            failed = True
        elif args.push and exported != target_head:
            subprocess.run(["git", "-C", str(root), "push", url, f"{exported}:refs/heads/{target}"], check=True)
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
