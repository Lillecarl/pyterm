"""
Print every probe's answer under every candidate this interpreter runs.

    python tests/matrix.py [--json]

The table `test_parity.py` holds is this output, read and judged.
"""

from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

sys.path[:0] = [str(Path(__file__).parent), str(Path(__file__).parent.parent)]

from lazylab import available
from probes import PROBES, observe


def main() -> None:
    with tempfile.TemporaryDirectory() as cache:
        table = {
            candidate: {probe: observe(candidate, probe, cache=Path(cache)) for probe in PROBES}
            for candidate in available()
        }
    if "--json" in sys.argv:
        print(json.dumps(table, indent=1))
        return
    for probe in PROBES:
        print(probe)
        for candidate, answers in table.items():
            print("    %-18s %s" % (candidate, json.dumps(answers[probe])))


main()
