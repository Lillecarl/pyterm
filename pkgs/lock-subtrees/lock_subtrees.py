"""
Write the `flake.lock` of each source from pyterm's own, or check them.

A source's flake has one input, `pyterm`, and builds its own directory
against its siblings there. So its lock is pyterm's lock graph with a
`pyterm` node on top, locked at a pyterm commit. Lillecarl/pymux#670.

A commit cannot name itself: its hash is not known until it exists. So the
locks name the commit under them, and land as a commit of their own that
changes nothing else. A source at that commit then builds against siblings
with the same code as its own.

    lock-subtrees            lock to HEAD, and commit the locks with jj
    lock-subtrees --check    exit 1 unless every lock names a commit that
                             only lock files have changed since

A source is a top-level directory with a tracked `flake.nix`.
"""

from __future__ import annotations

import argparse
import copy
import json
import subprocess
import sys
from pathlib import Path
from typing import Any, Final

OWNER: Final = "Lillecarl"
REPO: Final = "pyterm"
LOCK: Final = "flake.lock"

type Lock = dict[str, Any]


def git(root: Path, *args: str) -> str:
    return subprocess.run(["git", "-C", str(root), *args], check=True, capture_output=True, text=True).stdout.strip()


def sources(root: Path) -> list[str]:
    tracked = git(root, "ls-files", "--", "*/flake.nix").splitlines()
    return sorted(path.split("/")[0] for path in tracked if path.count("/") == 1)


def fetched(root: Path, rev: str) -> dict[str, Any]:
    """
    The narHash and lastModified of pyterm at `rev`, from the local
    repository. A `github:` fetch of the same revision gives the same
    narHash: measured on 3fc6e183.
    """
    expr = f'builtins.fetchTree {{ type = "git"; url = "file://{root}"; rev = "{rev}"; }}'
    out = subprocess.run(
        ["nix", "eval", "--impure", "--json", "--expr", f"{{ inherit ({expr}) narHash lastModified; }}"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout
    return json.loads(out)


def subtree_lock(root_lock: Lock, rev: str, narHash: str, lastModified: int) -> Lock:
    nodes = {name: copy.deepcopy(node) for name, node in root_lock["nodes"].items() if name != root_lock["root"]}
    if REPO in nodes:
        raise SystemExit(f"pyterm's own lock has a node named {REPO!r}, which the subtree lock needs")
    nodes[REPO] = {
        "inputs": copy.deepcopy(root_lock["nodes"][root_lock["root"]]["inputs"]),
        "locked": {
            "lastModified": lastModified,
            "narHash": narHash,
            "owner": OWNER,
            "repo": REPO,
            "rev": rev,
            "type": "github",
        },
        "original": {"owner": OWNER, "repo": REPO, "type": "github"},
    }
    nodes["root"] = {"inputs": {REPO: REPO}}
    return {"nodes": nodes, "root": "root", "version": root_lock["version"]}


def render(lock: Lock) -> str:
    # The layout nix writes, so `nix flake lock` in a clone changes nothing.
    return json.dumps(lock, indent=2, sort_keys=True) + "\n"


def write(root: Path) -> int:
    pending = [line for line in git(root, "status", "--porcelain").splitlines() if not line.endswith("/" + LOCK)]
    if pending:
        print("lock-subtrees: commit the work first; the locks name HEAD, and these are not in it:", file=sys.stderr)
        print("\n".join(pending), file=sys.stderr)
        return 1
    rev = git(root, "rev-parse", "HEAD")
    root_lock = json.loads((root / LOCK).read_text())
    meta = fetched(root, rev)
    written = []
    for name in sources(root):
        path = root / name / LOCK
        text = render(subtree_lock(root_lock, rev, meta["narHash"], meta["lastModified"]))
        if not path.exists() or path.read_text() != text:
            path.write_text(text)
            written.append(f"{name}/{LOCK}")
    if not written:
        print(f"lock-subtrees: every lock already names {rev[:12]}")
        return 0
    message = f"Lock the sources at pyterm {rev[:12]}\n\nWritten by lock-subtrees."
    subprocess.run(["jj", "--no-pager", "-R", str(root), "commit", "-m", message, *written], check=True)
    print(f"lock-subtrees: committed {len(written)} locks at {rev[:12]}")
    return 0


def check(root: Path, head: str) -> int:
    root_lock = json.loads((root / LOCK).read_text())
    failed = 0
    for name in sources(root):
        path = root / name / LOCK
        if not path.exists():
            print(f"{name}: no {LOCK}")
            failed = 1
            continue
        lock = json.loads(path.read_text())
        rev = lock["nodes"][REPO]["locked"]["rev"]
        changed = git(root, "diff", "--name-only", rev, head).splitlines()
        stale = [p for p in changed if not (p.endswith("/" + LOCK) and p.count("/") == 1)]
        meta = fetched(root, rev)
        wanted = render(subtree_lock(root_lock, rev, meta["narHash"], meta["lastModified"]))
        if stale:
            print(f"{name}: locked at {rev[:12]}, and {len(stale)} files changed since, such as {stale[0]}")
            failed = 1
        elif path.read_text() != wanted:
            print(f"{name}: {LOCK} is not what lock-subtrees writes for {rev[:12]}")
            failed = 1
        else:
            print(f"{name}: locked at {rev[:12]}")
    if failed:
        print("Run lock-subtrees after the last change, and push the commit it makes.")
    return failed


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--check", metavar="REV", nargs="?", const="HEAD", help="check the locks at REV (HEAD)")
    parser.add_argument("--root", type=Path, default=Path.cwd())
    args = parser.parse_args()
    root = Path(git(args.root, "rev-parse", "--show-toplevel"))
    if args.check:
        return check(root, git(root, "rev-parse", args.check))
    return write(root)


if __name__ == "__main__":
    sys.exit(main())
