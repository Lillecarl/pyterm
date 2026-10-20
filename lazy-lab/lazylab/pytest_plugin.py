"""
Install a candidate in a pytest run, workers included.

    LAZYLAB_CANDIDATE=ast-native LAZYLAB_POLICY=importers=pymux \
        python -m pytest -p lazylab.pytest_plugin ...

xdist starts each worker with the same `-p`, so each installs its own.
With `LAZYLAB_STAMPS` set, each process that installed leaves a file
there named for its pid: the proof that the workers ran lazy too.
"""

from __future__ import annotations

import os
from pathlib import Path

from . import install

_candidate = os.environ.get("LAZYLAB_CANDIDATE", "eager")
install(_candidate, os.environ.get("LAZYLAB_POLICY", "everything"))
if stamps := os.environ.get("LAZYLAB_STAMPS"):
    Path(stamps).mkdir(parents=True, exist_ok=True)
    (Path(stamps) / str(os.getpid())).write_text(_candidate)
