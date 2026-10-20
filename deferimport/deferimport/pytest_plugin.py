"""
Run a suite with every import it reaches made lazy.

    DEFERIMPORT_POLICY="deny=hypothesis,asyncssh" python -m pytest -p deferimport.pytest_plugin

xdist starts each worker with the same `-p`, so each installs its own.
`DEFERIMPORT=eager` runs the same command eager. A test module and a
conftest stay pytest's, for its assert rewriting.
"""

from __future__ import annotations

import os

from . import install

install(os.environ.get("DEFERIMPORT_POLICY", "everything"))
