"""
pymux's unit suite under each candidate, against the same suite eager.

    python measure/pymux_unit.py OUT PYMUX_SOURCE

Run from a copy of pymux's source: its `pymux`, `tests` and
`pyproject.toml`. Each candidate runs the whole suite. A failure the
eager run shares is the sandbox's, so the report lists only what a
candidate adds and what it fixes.

`LAZYLAB_PYMUX_CANDIDATES` picks the candidates, `LAZYLAB_PYMUX_POLICY`
the policy, and `LAZYLAB_PYMUX_TESTS` narrows the suite.
"""

from __future__ import annotations

import os
import re
import subprocess
import sys
from pathlib import Path

LAB = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(LAB))

from lazylab import available

OURS = "importers=pymux,libpymux,ptterm,ptyhost,pyte,txterm,pyterm_pytest"

_FAILED = re.compile(r"^(?:FAILED|ERROR) (\S+)")


def run(candidate: str, policy: str, out: Path, source: Path) -> tuple[set[str], int, str]:
    stamps = out / ("stamps-" + candidate)
    env = dict(os.environ)
    env.update(
        LAZYLAB_CANDIDATE=candidate,
        LAZYLAB_POLICY=policy,
        LAZYLAB_STAMPS=str(stamps),
        LAZYLAB_CACHE=str(out / "cache" / candidate),
        PYTHONPATH=os.pathsep.join(filter(None, [str(LAB), env.get("PYTHONPATH")])),
        PYTHONHASHSEED="0",
    )
    cores = min(int(os.environ.get("NIX_BUILD_CORES") or 8) or 8, 8)
    selection = os.environ.get("LAZYLAB_PYMUX_TESTS", "").split()
    argv = [
        sys.executable,
        "-m",
        "pytest",
        "-p",
        "lazylab.pytest_plugin",
        "-q",
        "-rfE",
        "-p",
        "no:cacheprovider",
        "-n",
        str(cores),
        "--dist",
        "worksteal",
        "-o",
        "faulthandler_timeout=120",
        *selection,
    ]
    done = subprocess.run(argv, env=env, cwd=source, capture_output=True, text=True, check=False)
    (out / ("log-" + candidate)).write_text(done.stdout + done.stderr)
    failed = {m[1] for line in done.stdout.splitlines() if (m := _FAILED.match(line))}
    tail = next((line for line in reversed(done.stdout.splitlines()) if line.strip()), "")
    workers = len(list(stamps.iterdir())) if stamps.exists() else 0
    return failed, workers, tail


def main(out: Path, source: Path) -> None:
    out.mkdir(parents=True, exist_ok=True)
    policy = os.environ.get("LAZYLAB_PYMUX_POLICY", OURS)
    chosen = os.environ.get("LAZYLAB_PYMUX_CANDIDATES", "").split() or available()
    if "eager" not in chosen:
        chosen.insert(0, "eager")
    lines = ["# pymux-unit, Python %s, policy `%s`" % (sys.version.split()[0], policy), ""]
    eager: set[str] = set()
    for candidate in chosen:
        failed, workers, tail = run(candidate, policy, out, source)
        print(candidate, len(failed), "failed;", workers, "processes installed;", tail, flush=True)
        if candidate == "eager":
            eager = failed
            lines += ["eager: %s (%d processes installed)" % (tail, workers)]
            lines += ["- " + name for name in sorted(failed)] + [""]
            continue
        lines += ["## %s" % candidate, "", "%s (%d processes installed)" % (tail, workers), ""]
        lines += ["Fails only here:"] + (["- " + name for name in sorted(failed - eager)] or ["- nothing"])
        lines += ["", "Passes only here:"] + (["- " + name for name in sorted(eager - failed)] or ["- nothing"]) + [""]
    (out / "report.md").write_text("\n".join(lines))
    print("\n".join(lines))


if __name__ == "__main__":
    main(Path(sys.argv[1]), Path(sys.argv[2]))
