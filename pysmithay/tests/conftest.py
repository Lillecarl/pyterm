from __future__ import annotations

import pytest

from pysmithay import Compositor


@pytest.fixture
def compositor(tmp_path, monkeypatch):
    "A compositor on a runtime directory of its own."
    runtime = tmp_path / "run"
    runtime.mkdir(mode=0o700)
    monkeypatch.setenv("XDG_RUNTIME_DIR", str(runtime))
    return Compositor()
