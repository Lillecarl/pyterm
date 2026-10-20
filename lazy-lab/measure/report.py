"""
Every workload under every candidate and policy, as one report.

    python measure/report.py OUT [PYMUX_TESTS]

OUT gets `results.json` and `report.md`. With PYMUX_TESTS, the
directory of pymux's `tests`, it also runs `measure_frame.py` under
each candidate: pymux's own frame count, against the same count eager.

A run that fails is a result, not a crash: its row says how it ended.
A rewrite candidate that made nothing lazy under a policy that names
work for it raises instead, because its row would read as "no cost".
"""

from __future__ import annotations

import json
import os
import re
import statistics
import subprocess
import sys
import tempfile
from pathlib import Path

LAB = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(LAB))

from lazylab import available
from lazylab.policy import PRESETS as POLICIES

WORKLOADS = ("import-server", "completion")

#: Clock runs per row; the median is reported.
TIMINGS = int(os.environ.get("LAZYLAB_TIMINGS", "5"))

_FRAME_ROW = re.compile(r"^(?P<name>\S.*?\)) +(?P<count>\d+) +budget +(?P<budget>\d+)")


def _env(cache: Path) -> dict[str, str]:
    env = dict(os.environ)
    env["PYTHONPATH"] = os.pathsep.join(filter(None, [str(LAB), env.get("PYTHONPATH")]))
    env["LAZYLAB_CACHE"] = str(cache)
    env["PYTHONHASHSEED"] = "0"
    return env


def _run(argv: list[str], env: dict[str, str], cwd: Path | None = None) -> tuple[int, str, str]:
    done = subprocess.run(argv, env=env, cwd=cwd, capture_output=True, text=True, timeout=900, check=False)
    return done.returncode, done.stdout, done.stderr


def _ended(code: int, stderr: str) -> str:
    last = [line for line in stderr.splitlines() if line.strip()]
    return "exit %d: %s" % (code, last[-1] if last else "")


def workload(candidate: str, policy: str, name: str, cache: Path) -> dict:
    argv = [sys.executable, "-m", "lazylab", candidate, policy, str(LAB / "measure" / "workload.py"), name]
    env = _env(cache)
    # The first run fills the rewrite cache, so the counted one reads
    # bytecode the way an installed package does.
    _run([*argv, "count"], env)
    code, out, err = _run([*argv, "count"], env)
    if code:
        return {"error": _ended(code, err)}
    row = json.loads(out.rsplit("RESULT ", 1)[1])
    seconds = []
    for _ in range(TIMINGS):
        code, out, err = _run([*argv, "time"], env)
        if code:
            return row | {"error": _ended(code, err)}
        seconds.append(json.loads(out.rsplit("RESULT ", 1)[1])["seconds"])
    row["seconds"] = statistics.median(seconds)
    return row


def frame(candidate: str, policy: str, tests: Path, cache: Path) -> dict:
    env = _env(cache) | {"PYMUX_FRAME_OUT": tempfile.mkdtemp()}
    argv = [sys.executable, "-m", "lazylab", candidate, policy, str(tests / "measure_frame.py")]
    _run(argv, env, cwd=tests.parent)
    code, out, err = _run(argv, env, cwd=tests.parent)
    rows = {m["name"]: int(m["count"]) for line in out.splitlines() if (m := _FRAME_ROW.match(line))}
    if not rows:
        return {"error": _ended(code, err)}
    return rows


def main(out: Path, tests: Path | None) -> None:
    out.mkdir(parents=True, exist_ok=True)
    results: dict = {"python": sys.version.split()[0], "rows": []}
    for policy_name, policy in POLICIES.items():
        for candidate in available():
            if candidate == "eager" and policy_name != "ours":
                continue
            with tempfile.TemporaryDirectory() as cache:
                row: dict = {"candidate": candidate, "policy": policy_name}
                for name in WORKLOADS:
                    row[name] = workload(candidate, policy, name, Path(cache))
                    print(candidate, policy_name, name, row[name], flush=True)
                if tests is not None:
                    row["frame"] = frame(candidate, policy, tests, Path(cache))
                    print(candidate, policy_name, "frame", row["frame"], flush=True)
            if candidate.startswith("ast-") and not row["import-server"].get("error"):
                if row["import-server"]["lazy"] == 0:
                    raise SystemExit("%s under %s rewrote nothing" % (candidate, policy_name))
            results["rows"].append(row)
    (out / "results.json").write_text(json.dumps(results, indent=1))
    (out / "report.md").write_text(render(results))
    print(render(results))


def _cell(value: dict, key: str, eager: dict | None, scale: float = 1.0, digits: int = 0) -> str:
    if "error" in value:
        return "**%s**" % value["error"][:60]
    number = value[key] * scale
    text = "%.*f" % (digits, number)
    if eager and "error" not in eager and eager.get(key):
        text += " (%+.0f%%)" % ((value[key] / eager[key] - 1) * 100)
    return text


def render(results: dict) -> str:
    rows = results["rows"]
    eager = next(row for row in rows if row["candidate"] == "eager")
    lines = ["# Python %s" % results["python"], ""]
    for name in WORKLOADS:
        lines += [
            "## %s" % name,
            "",
            "| candidate | policy | modules run | lazy | instructions | ms (median) | commands |",
            "| --- | --- | --- | --- | --- | --- | --- |",
        ]
        for row in rows:
            value, base = row[name], eager[name]
            lines.append(
                "| %s | %s | %s | %s | %s | %s | %s |"
                % (
                    row["candidate"],
                    row["policy"],
                    _cell(value, "modules", base),
                    value.get("lazy", ""),
                    _cell(value, "instructions", base),
                    _cell(value, "seconds", base, 1000, 1) if "seconds" in value else "",
                    value.get("commands", ""),
                )
            )
        lines.append("")
    if "frame" in eager:
        # One row per run: each kind of measurement over every shape, as
        # the mean and the worst change against eager.
        kinds = ["measure", "frame", "neighbours", "neighbours cold"]
        lines += ["## frame (instructions against eager: mean / worst over the shapes)", ""]
        lines += ["| candidate | policy | " + " | ".join(kinds) + " |", "| --- | --- |" + " --- |" * len(kinds)]
        for row in rows[1:]:
            if "error" in row["frame"]:
                lines.append("| %s | %s | **%s** |" % (row["candidate"], row["policy"], row["frame"]["error"][:80]))
                continue
            cells = []
            for kind in kinds:
                changes = [
                    (count / eager["frame"][shape] - 1) * 100
                    for shape, count in row["frame"].items()
                    if shape.endswith("(%s)" % kind) and eager["frame"].get(shape)
                ]
                cells.append("%+.1f%% / %+.1f%%" % (sum(changes) / len(changes), max(changes)) if changes else "")
            lines.append("| %s | %s | %s |" % (row["candidate"], row["policy"], " | ".join(cells)))
        lines.append("")
    return "\n".join(lines)


if __name__ == "__main__":
    main(Path(sys.argv[1]), Path(sys.argv[2]) if len(sys.argv) > 2 else None)
