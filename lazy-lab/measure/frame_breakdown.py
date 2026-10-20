"""
Where a frame measurement's instructions go, by code object.

    python -m lazylab CANDIDATE POLICY measure/frame_breakdown.py PYMUX_TESTS SHAPE

Runs `measure_frame.measurements` for the shapes matching SHAPE, counts
each one by `co_qualname`, and prints the code objects as JSON. Two runs,
eager and a candidate, say which code a candidate's extra instructions
are spent in.
"""

from __future__ import annotations

import collections
import json
import sys

_TOOL = sys.monitoring.PROFILER_ID


def by_code(work) -> collections.Counter:
    counts: collections.Counter = collections.Counter()

    def one(code, offset):
        counts["%s:%s" % (code.co_filename.rsplit("/", 1)[-1], code.co_qualname)] += 1

    sys.monitoring.use_tool_id(_TOOL, "lazylab-breakdown")
    sys.monitoring.register_callback(_TOOL, sys.monitoring.events.INSTRUCTION, one)
    sys.monitoring.set_events(_TOOL, sys.monitoring.events.INSTRUCTION)
    try:
        work()
    finally:
        sys.monitoring.set_events(_TOOL, 0)
        sys.monitoring.free_tool_id(_TOOL)
    return counts


def main(tests: str, shape: str) -> None:
    sys.path.insert(0, tests)
    import measure_frame

    found, pymux = measure_frame.measurements(shape)
    answer = {}
    # As `measure_frame.main` runs each one.
    for name, work, state in found:
        pymux.state = state
        try:
            with measure_frame.create_application(
                measure_frame.create_container(pymux, *measure_frame.create_window(1))
            ):
                counts = by_code(work)
        finally:
            pymux.state = None
        answer[name] = dict(counts.most_common())
    print("RESULT " + json.dumps(answer))


main(*sys.argv[1:])
