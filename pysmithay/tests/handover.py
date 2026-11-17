"""
A parent that hands its compositor child to the next image of itself,
across an `exec`, as an upgrading server does. Lillecarl/pyterm#1004.

    handover.py                           start a child and a probe window, pause, exec
    handover.py --adopt FD VERSION PID W  adopt the child, and print what it holds

The adopting image prints one JSON line: the windows `adopt` answered,
the frame of the first, and how the child ended once let go.
"""

from __future__ import annotations

import asyncio
import json
import os
import select
import socket
import subprocess
import sys
import time
from pathlib import Path

from pysmithay import RemoteCompositor
from pysmithay.host import command

CLIENT = Path(__file__).with_name("client.py")
TIMEOUT = 10.0


def pump(compositor, until):
    seen = []
    deadline = time.monotonic() + TIMEOUT
    while not until(seen):
        if time.monotonic() > deadline:
            raise TimeoutError("saw %r" % (seen,))
        select.select(compositor.fds(), [], [], 0.1)
        events = compositor.dispatch()
        seen.extend(events)
        for event in events:
            if event[0] == "commit":
                compositor.frame_done(event[1], 0)
    return seen


def hand_over() -> None:
    ours, theirs = socket.socketpair()
    child = subprocess.Popen(command(theirs.fileno()), pass_fds=(theirs.fileno(),))
    theirs.close()
    compositor = asyncio.run(_started(ours.detach()))
    tag, fd = compositor.connect()
    # The window holds until its stdin closes: this end crosses the exec.
    hold, holding = os.pipe()
    subprocess.Popen(
        [sys.executable, str(CLIENT)], env=dict(os.environ, WAYLAND_SOCKET=str(fd)), pass_fds=[fd], stdin=hold
    )
    os.close(fd)
    os.close(hold)
    pump(compositor, lambda seen: any(event[0] == "commit" for event in seen))
    compositor.pause()
    carried = compositor.fileno()
    os.set_inheritable(carried, True)
    os.set_inheritable(holding, True)
    argv = [sys.executable, __file__, "--adopt", str(carried), str(compositor.version), str(child.pid), str(holding)]
    os.execv(sys.executable, argv)


async def _started(fd: int) -> RemoteCompositor:
    return await RemoteCompositor.start(fd)


async def _adopted(fd: int, version: int) -> tuple[RemoteCompositor, list]:
    return await RemoteCompositor.adopt(fd, version)


def adopt(fd: int, version: int, pid: int, holding: int) -> None:
    os.set_inheritable(fd, False)
    compositor, windows = asyncio.run(_adopted(fd, version))
    (id, *_rest) = windows[0]
    width, height, _rgba = compositor.frame(id)
    os.close(holding)
    pump(compositor, lambda seen: ("closed", id) in seen)
    compositor.shutdown()
    _pid, status = os.waitpid(pid, 0)
    print(json.dumps({"windows": windows, "frame": [width, height], "exit": os.waitstatus_to_exitcode(status)}))


if __name__ == "__main__":
    if sys.argv[1:2] == ["--adopt"]:
        adopt(*(int(argument) for argument in sys.argv[2:6]))
    else:
        hand_over()
