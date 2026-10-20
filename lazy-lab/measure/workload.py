"""
Run one workload in this interpreter and print what it cost, as JSON.

    python -m lazylab CANDIDATE POLICY measure/workload.py NAME count|time

`count` counts bytecode instructions with `sys.monitoring`, which is
the same on every run. `time` reads a clock, which is not, and is
there for a person to read beside the count. The two never run in
one process: the counting slows the clock.
"""

from __future__ import annotations

import importlib
import json
import sys
import time

import lazylab


def _import_server():
    importlib.import_module("pymux.server")
    return {}


def _completion():
    parser = importlib.import_module("pymux.entry_points.run_pymux")._completion_parser()
    modes = next(action for action in parser._actions if action.__class__.__name__ == "_SubParsersAction")
    # A command lost to a deferred import shows here.
    return {"commands": len(modes.choices)}


WORKLOADS = {
    "import-server": _import_server,
    "completion": _completion,
}


def _ran() -> int:
    "Modules whose code ran: LazyLoader puts one in before it runs."
    return sum(1 for module in list(sys.modules.values()) if type(module).__name__ != "_LazyModule")


def _counted(work) -> tuple[int, dict]:
    counted = 0

    def one(code, offset):
        nonlocal counted
        counted += 1

    tool = sys.monitoring.PROFILER_ID
    sys.monitoring.use_tool_id(tool, "lazylab")
    sys.monitoring.register_callback(tool, sys.monitoring.events.INSTRUCTION, one)
    sys.monitoring.set_events(tool, sys.monitoring.events.INSTRUCTION)
    try:
        extra = work()
    finally:
        sys.monitoring.set_events(tool, 0)
        sys.monitoring.free_tool_id(tool)
    return counted, extra


def main(name: str, how: str) -> None:
    work = WORKLOADS[name]
    before = _ran()
    if how == "count":
        instructions, extra = _counted(work)
        answer = {"instructions": instructions}
    else:
        started = time.perf_counter()
        extra = work()
        answer = {"seconds": time.perf_counter() - started}
    answer.update(extra, modules=_ran() - before, lazy=lazylab.lazy_count())
    print("RESULT " + json.dumps(answer))


main(*sys.argv[1:])
