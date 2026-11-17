from __future__ import annotations

import asyncio
import os
import socket
import subprocess

import pytest

from pysmithay import Compositor, RemoteCompositor
from pysmithay.host import command


@pytest.fixture(params=["here", "child"])
def compositor(request, tmp_path, monkeypatch):
    """
    A compositor on a runtime directory of its own: in this process, and
    in a child behind `RemoteCompositor`, which every test judges the
    same. Lillecarl/pyterm#1004.
    """
    runtime = tmp_path / "run"
    runtime.mkdir(mode=0o700)
    monkeypatch.setenv("XDG_RUNTIME_DIR", str(runtime))
    if request.param == "here":
        yield Compositor()
        return
    ours, theirs = socket.socketpair()
    child = subprocess.Popen(command(theirs.fileno()), pass_fds=(theirs.fileno(),), env=os.environ)
    theirs.close()
    remote = asyncio.run(_started(ours.detach()))
    try:
        yield remote
    finally:
        remote.shutdown()
        assert child.wait(timeout=10) == 0


async def _started(fd: int) -> RemoteCompositor:
    return await RemoteCompositor.start(fd)
