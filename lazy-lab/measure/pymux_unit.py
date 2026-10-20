"""
pymux's unit suite under each candidate and policy, against eager.

    python measure/pymux_unit.py OUT PYMUX_SOURCE

Run from a copy of pymux's source: its `pymux`, `tests` and
`pyproject.toml`. A failure the eager run shares is the sandbox's, so
the report lists what each run adds and what it fixes, and groups what
it adds by the reason pytest printed: with "everything" the suite is
the judge of a recursive rewrite, and a reason names a cause.

`LAZYLAB_PYMUX_CANDIDATES` picks the candidates, `LAZYLAB_PYMUX_POLICIES`
the policies (preset names or specs, space-separated), and
`LAZYLAB_PYMUX_TESTS` narrows the suite.
"""

from __future__ import annotations

import collections
import os
import re
import subprocess
import sys
from pathlib import Path
from xml.etree import ElementTree

LAB = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(LAB))

from lazylab import available

#: `FAILED tests/x.py::test - TypeError: ...`, as `-rfE` prints it.
_FAILED = re.compile(r"^(?:FAILED|ERROR) (\S+)(?: - (.*))?")


def run(candidate: str, policy: str, out: Path, source: Path) -> tuple[dict[str, str], int, str]:
    label = "%s-%s" % (candidate, re.sub(r"\W+", "_", policy))
    stamps = out / ("stamps-" + label)
    env = dict(os.environ)
    env.update(
        LAZYLAB_CANDIDATE=candidate,
        LAZYLAB_POLICY=policy,
        LAZYLAB_STAMPS=str(stamps),
        LAZYLAB_CACHE=str(out / "cache" / label),
        PYTHONPATH=os.pathsep.join(filter(None, [str(LAB), env.get("PYTHONPATH")])),
        PYTHONHASHSEED="0",
    )
    cores = min(int(os.environ.get("NIX_BUILD_CORES") or 8) or 8, 8)
    selection = os.environ.get("LAZYLAB_PYMUX_TESTS", "").split()
    junit = out / ("junit-" + label + ".xml")
    argv = [
        *(sys.executable, "-m", "pytest", "-p", "lazylab.pytest_plugin", "-q", "-rfE"),
        *("-p", "no:cacheprovider", "-n", str(cores), "--dist", "worksteal"),
        *("-o", "faulthandler_timeout=120", "--junitxml", str(junit)),
        *selection,
    ]
    done = subprocess.run(argv, env=env, cwd=source, capture_output=True, text=True, check=False)
    (out / ("log-" + label)).write_text(done.stdout + done.stderr)
    # A run that died before writing the report has only the summary
    # lines, which name a test another way: one source per run.
    failed = (
        _junit_failures(junit)
        if junit.exists()
        else {m[1]: (m[2] or "").strip() for line in done.stdout.splitlines() if (m := _FAILED.match(line))}
    )
    tail = next((line for line in reversed(done.stdout.splitlines()) if line.strip()), "")
    if not tail:
        tail = next((line for line in reversed(done.stderr.splitlines()) if line.strip()), "")
    workers = len(list(stamps.iterdir())) if stamps.exists() else 0
    return failed, workers, tail


def _junit_failures(path: Path) -> dict[str, str]:
    "Each failed test and the first line of why, from pytest's JUnit report."
    if not path.exists():
        return {}
    failed = {}
    for case in ElementTree.parse(path).iter("testcase"):
        for outcome in case:
            if outcome.tag in ("failure", "error"):
                name = "%s::%s" % (case.get("classname", ""), case.get("name", ""))
                failed[name] = (outcome.get("message") or "").splitlines()[0] if outcome.get("message") else ""
    return failed


def _reasons(failed: dict[str, str], only: set[str]) -> list[str]:
    "Failures grouped by their reason, the commonest first."
    groups: dict[str, list[str]] = collections.defaultdict(list)
    for name in only:
        groups[failed[name][:160] or "(no reason printed)"].append(name)
    lines = []
    for reason, names in sorted(groups.items(), key=lambda kv: -len(kv[1])):
        lines.append("- %d: `%s`" % (len(names), reason))
        lines += ["  - " + name for name in sorted(names)[:5]]
        if len(names) > 5:
            lines.append("  - and %d more" % (len(names) - 5))
    return lines or ["- nothing"]


def main(out: Path, source: Path) -> None:
    out.mkdir(parents=True, exist_ok=True)
    policies = os.environ.get("LAZYLAB_PYMUX_POLICIES", "").split() or ["everything", "ours"]
    chosen = [name for name in os.environ.get("LAZYLAB_PYMUX_CANDIDATES", "").split() or available() if name != "eager"]
    failed, workers, tail = run("eager", "everything", out, source)
    eager = set(failed)
    print("eager", len(eager), "failed;", tail, flush=True)
    lines = ["# pymux-unit, Python %s" % sys.version.split()[0], ""]
    lines += ["eager: %s" % tail] + ["- " + name for name in sorted(eager)] + [""]
    for policy in policies:
        for candidate in chosen:
            failed, workers, tail = run(candidate, policy, out, source)
            added = set(failed) - eager
            print(candidate, policy, len(added), "added;", workers, "processes installed;", tail, flush=True)
            lines += ["## %s, `%s`" % (candidate, policy), "", "%s (%d processes installed)" % (tail, workers), ""]
            lines += ["Fails only here, by reason:", *_reasons(failed, added)]
            fixed = sorted(eager - set(failed))
            lines += ["", "Passes only here:"] + (["- " + name for name in fixed] or ["- nothing"]) + [""]
    (out / "report.md").write_text("\n".join(lines))
    print("\n".join(lines))


if __name__ == "__main__":
    main(Path(sys.argv[1]), Path(sys.argv[2]))
