#!/usr/bin/env python3
"""
A Claude Code PostToolUse hook: ruff's safe fixes, then the formatter, on
each Python file an edit just wrote.

Each source's own `pyproject.toml` decides the rules, because ruff reads
the configuration nearest to each file. What ruff cannot fix goes to
stderr with exit 2, which Claude Code shows to the agent; a clean run
prints nothing.

It reads the edits of the Edit, MultiEdit and Write tools, and the files
of a pyedit run that applied.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

#: Upstream's code, with its own style; see `pyedit.toml`.
SKIPPED = ("prompt-toolkit/",)


def _texts(value: object):
    "Every string inside a tool response, however the tool nested it."
    if isinstance(value, str):
        yield value
    elif isinstance(value, dict):
        for each in value.values():
            yield from _texts(each)
    elif isinstance(value, list):
        for each in value:
            yield from _texts(each)


def _pyedit_files(response: object) -> list[str]:
    "The files a pyedit run wrote: its result names them, relative to the repository."
    for text in _texts(response):
        try:
            result = json.loads(text)
        except ValueError:
            continue
        if isinstance(result, dict) and result.get("applied") and isinstance(result.get("files"), list):
            return [str(each) for each in result["files"]]
    return []


def _written(event: dict) -> list[Path]:
    tool = event.get("tool_name", "")
    if tool in ("Edit", "MultiEdit", "Write"):
        names = [event.get("tool_input", {}).get("file_path", "")]
    elif tool.endswith("pyedit__run"):
        names = _pyedit_files(event.get("tool_response"))
    else:
        return []
    paths = []
    for name in names:
        path = Path(name) if Path(name).is_absolute() else ROOT / name
        try:
            relative = path.resolve().relative_to(ROOT).as_posix()
        except ValueError:
            continue
        if path.suffix == ".py" and path.is_file() and not relative.startswith(SKIPPED):
            paths.append(path)
    return paths


def main() -> int:
    paths = [str(each) for each in _written(json.load(sys.stdin))]
    if not paths:
        return 0
    checked = subprocess.run(
        ["ruff", "check", "--fix", "--quiet", *paths], cwd=ROOT, capture_output=True, text=True
    )
    subprocess.run(["ruff", "format", "--quiet", *paths], cwd=ROOT, capture_output=True, text=True)
    if checked.returncode != 0:
        sys.stderr.write("ruff left these for you to fix:\n" + checked.stdout + checked.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
