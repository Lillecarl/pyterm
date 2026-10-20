"""
Run a program with a candidate installed first.

    python -m lazylab CANDIDATE POLICY -m pytest -q tests
    python -m lazylab CANDIDATE POLICY -c "import pymux.server"
    python -m lazylab CANDIDATE POLICY script.py args...
"""

from __future__ import annotations

import os
import runpy
import sys

from . import install


def main(argv: list[str]) -> None:
    if len(argv) < 3:
        raise SystemExit(__doc__)
    candidate, policy, *rest = argv
    install(candidate, policy)
    match rest:
        case ["-m", module, *args]:
            sys.argv = [module, *args]
            runpy.run_module(module, run_name="__main__", alter_sys=True)
        case ["-c", code, *args]:
            sys.argv = ["-c", *args]
            exec(compile(code, "<string>", "exec"), {"__name__": "__main__"})
        case [script, *args]:
            sys.argv = [script, *args]
            # As `python script.py` does, so the script's siblings import.
            sys.path.insert(0, os.path.dirname(os.path.abspath(script)))
            runpy.run_path(script, run_name="__main__")
        case _:
            raise SystemExit(__doc__)


main(sys.argv[1:])
