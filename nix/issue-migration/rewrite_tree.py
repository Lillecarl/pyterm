"""pyedit script: point every reference to a moved issue at its new number.

  cd $(mktemp -d) && PYTERM=~/Code/pyterm pyedit -s ~/Code/pyterm/nix/issue-migration/rewrite_tree.py [--apply]

Run it from outside the tree: the root's pyedit.toml would put every staged
`.py` file through ruff's language server, which reformats more than this
changes and outlasts pyedit's timeout over a thousand files.

`Lillecarl/pymux#N` and `github.com/Lillecarl/pymux/issues/N` become
`Lillecarl/pyterm#M` and its URL through the `moves` table, and a link to
the pymux tracker becomes a link to pyterm's. A bare `#N` is rewritten only
where BARE names it: most bare numbers in the tree are a sixel colour, a
vttest screen or another project's issue.
"""

import os
import re
import sqlite3
import subprocess
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(os.environ["PYTERM"]).expanduser()
HERE = ROOT / "nix/issue-migration"
db = sqlite3.connect(HERE / "issues.sqlite")
NEW = {(repo, old): new for repo, old, new in db.execute("select repo, old, new from moves")}
assert len(NEW) == db.execute("select count(*) from issues").fetchone()[0], "the transfer is not finished"

#: path -> line -> the old numbers written bare on that line.
BARE: dict[str, dict[int, list[int]]] = {
    "ptterm/ptterm/copy_mode.py": {480: [189]},
    "ptterm/tests/test_the_layers.py": {12: [85], 13: [82]},
    "pymux/docs/layout-engine-plan.md": {29: [198, 210, 211]},
    "pymux/docs/tmux-compat-decisions.md": {12: [395, 384]},
    "pymux/docs/window-pane-support.md": {
        12: [620],
        13: [634],
        14: [639, 649, 644],
        15: [643],
        16: [648],
        17: [650],
    },
    "pymux/libpymux/libpymux/protocol.py": {10: [446]},
    "pymux/libpymux/libpymux/wire.py": {58: [633]},
    "pymux/pymux/commands/if_shell.py": {30: [311]},
    "pymux/pymux/commands/set_client_option.py": {54: [199]},
    "pymux/pymux/connection/pacing.py": {3: [825]},
    "pymux/pymux/core/main.py": {744: [289]},
    "pymux/pymux/keys/key_bindings.py": {767: [396]},
    "pymux/pymux/layout/command_line.py": {210: [148, 48]},
    "pymux/pymux/style/style.py": {175: [161]},
    "pymux/pymux/style/style_pygments.py": {16: [194]},
    "pymux/tests/drive_with_pty.py": {1115: [369]},
    "pymux/tests/fixtures/tmux37/accepted_product_divergences.txt": {4: [384]},
    "pymux/tests/measure_images.py": {8: [575]},
    "pymux/tests/measure_loop_stalls.py": {59: [632]},
    "pymux/tests/measure_scrolling.py": {27: [512], 28: [507]},
    "pymux/tests/photograph_vttest.py": {73: [116, 117], 74: [117]},
    "pymux/tests/picture-differences.txt": {165: [369]},
    "pymux/tests/reference/tmux_compat/divergences.toml": {17: [395], 21: [384]},
    "pymux/tests/scenario-differences.txt": {12: [371, 539]},
    "pymux/tests/test_a_client_has_a_name.py": {74: [340]},
    "pymux/tests/test_a_refused_client.py": {79: [332]},
    "pymux/tests/test_a_slow_client.py": {4: [629]},
    "pymux/tests/test_capture_pane.py": {55: [476]},
    "pymux/tests/test_command_line_answers.py": {7: [289, 292]},
    "pymux/tests/test_openssh_interop.py": {284: [587]},
    "pymux/tests/test_respawn.py": {71: [306]},
    "pymux/tests/test_session_options.py": {95: [756]},
    "pymux/tests/test_strip_draws.py": {248: [617]},
    "pymux/tests/test_strip_plan.py": {320: [617], 433: [617]},
    "pymux/tests/test_strip_scroll_is_stable.py": {145: [617], 218: [617]},
    "pymux/tests/test_theme.py": {149: [161]},
    "pymux/tests/test_update_environment.py": {2: [271]},
    "pyte/nix/checks.nix": {201: [684]},
    "pyte/tests/test_keys_against_kitty.py": {153: [684]},
}

BARE_NUMBER = re.compile(r"(?<![\w/&])#(\d+)\b")
ISSUE_URL = re.compile(r"github\.com/Lillecarl/pymux/issues/(\d+)\b")
TRACKER = re.compile(r"(\[Lillecarl/)pymux(\]\(https://github\.com/Lillecarl/)pymux(/issues\))")
TRACKER_URL = re.compile(r"github\.com/Lillecarl/pymux/issues\b")
# `\nLillecarl/pymux#232` sits in a string literal, after an escaped newline.
QUALIFIED = re.compile(r"(?:(?<![\w/.-])|(?<=\\n))Lillecarl/pymux#(\d+)\b")

stats: Counter[str] = Counter()
unmapped: Counter[str] = Counter()


def new_number(old: str, ref: str) -> int | None:
    new = NEW.get(("pymux", int(old)))
    if new is None:
        unmapped[ref] += 1
    return new


def issue_url(m: re.Match[str]) -> str:
    new = new_number(m[1], m[0])
    if new is None:
        return m[0]
    stats["url"] += 1
    return f"github.com/Lillecarl/pyterm/issues/{new}"


def qualified(m: re.Match[str]) -> str:
    new = new_number(m[1], m[0])
    if new is None:
        return m[0]
    stats["qualified"] += 1
    return f"Lillecarl/pyterm#{new}"


def tracker(m: re.Match[str]) -> str:
    stats["tracker"] += 1
    return f"{m[1]}pyterm{m[2]}pyterm{m[3]}"


def tracker_url(m: re.Match[str]) -> str:
    stats["tracker"] += 1
    return "github.com/Lillecarl/pyterm/issues"


def bare(path: str, text: str) -> str:
    lines = text.split("\n")
    for number, olds in BARE[path].items():
        seen: list[int] = []

        def one(m: re.Match[str], olds: list[int] = olds, seen: list[int] = seen) -> str:
            old = int(m[1])
            if old not in olds:
                return m[0]
            seen.append(old)
            stats["bare"] += 1
            return f"#{NEW[('pymux', old)]}"

        # One pass, so a new number is never read again as an old one.
        lines[number - 1] = BARE_NUMBER.sub(one, lines[number - 1])
        if sorted(seen) != sorted(olds):
            raise ValueError(f"{path}:{number}: wanted bare {olds}, found {seen} in {lines[number - 1]!r}")
    return "\n".join(lines)


files = subprocess.run(["git", "-C", str(ROOT), "ls-files", "-z"], capture_output=True, text=True, check=True).stdout.split("\0")
for path in filter(None, files):
    if path.startswith("nix/issue-migration/") or path.endswith((".lock", ".patch", ".png", ".svg", ".gif", ".bin")):
        continue
    # git lists a submodule's directory as a path.
    if not (ROOT / path).is_file():
        continue
    text = pyedit.read(str(ROOT / path))
    if not isinstance(text, str):
        continue
    # Bare numbers first: their line numbers are the file's as it is on disk.
    new = bare(path, text) if path in BARE else text
    new = ISSUE_URL.sub(issue_url, new)
    new = TRACKER.sub(tracker, new)
    new = TRACKER_URL.sub(tracker_url, new)
    new = QUALIFIED.sub(qualified, new)
    if new != text:
        pyedit.write(str(ROOT / path), new)

missing = set(BARE) - set(files)
assert not missing, f"BARE names files that are not tracked: {missing}"
print(dict(stats), file=sys.stderr)
print("unmapped:", dict(unmapped.most_common()), file=sys.stderr)
