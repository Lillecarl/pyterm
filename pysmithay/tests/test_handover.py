"""
A compositor child that another parent takes over: paused at a message
boundary, carried across an `exec`, adopted. Lillecarl/pyterm#1004.
"""

from __future__ import annotations

import json
import os
import select
import subprocess
import sys
import time
from pathlib import Path

import pytest
from test_compositor import CLIENT, commits, launch, pump

from pysmithay import Compositor

HANDOVER = Path(__file__).with_name("handover.py")
PROBE = ("probe", "pysmithay.probe")
SQUARE = (10, 5, 4, 4)


@pytest.fixture
def child(compositor):
    if isinstance(compositor, Compositor):
        pytest.skip("only a compositor in a child is handed over")
    return compositor


def test_a_compositor_names_each_open_window(compositor, tmp_path):
    if not isinstance(compositor, Compositor):
        pytest.skip("`resume` and `adopt` answer the windows of a child")
    tag, fd = compositor.connect()
    client = subprocess.Popen(
        [sys.executable, str(CLIENT)],
        env=dict(os.environ, WAYLAND_SOCKET=str(fd)),
        pass_fds=[fd],
        stdin=subprocess.PIPE,
    )
    os.close(fd)
    pump(compositor, lambda seen: ("app_id", 1, PROBE[1]) in seen)

    assert compositor.windows() == [(1, tag, *PROBE)]

    client.stdin.close()
    pump(compositor, lambda seen: ("closed", 1) in seen)
    client.wait(10)


def test_a_paused_child_writes_nothing_and_resumes_with_its_windows(child):
    client = launch(child, sys.executable, str(CLIENT))
    # Both frames, so that the probe waits on its stdin.
    pump(child, lambda seen: len(commits(seen)) >= 2)

    child.pause()
    client.stdin.close()
    client.wait(10)
    assert select.select(child.fds(), [], [], 0.5)[0] == []

    assert child.resume() == []
    with pytest.raises(KeyError):
        child.frame(1)


def test_a_resumed_window_draws_again_once_told_its_frame(child):
    """
    A commit held through the pause is gone: the window that made it
    waits on a frame done that only the new parent can send.
    """
    client = launch(child, sys.executable, str(CLIENT))
    pump(child, lambda seen: ("app_id", 1, PROBE[1]) in seen)

    child.pause()
    time.sleep(0.3)
    # Refused at once: a paused child answers nothing.
    with pytest.raises(KeyError):
        child.frame(1)
    assert child.resume() == [(1, 0, *PROBE)]
    assert child.frame(1)[:2] == (64, 32)
    child.frame_done(1, 0)
    pump(child, lambda seen: ("commit", 1, [SQUARE]) in seen)

    client.stdin.close()
    pump(child, lambda seen: ("closed", 1) in seen)
    client.wait(10)


def test_a_child_crosses_an_exec_with_its_window(tmp_path):
    runtime = tmp_path / "run"
    runtime.mkdir(mode=0o700)
    env = dict(os.environ, XDG_RUNTIME_DIR=str(runtime))
    done = subprocess.run([sys.executable, str(HANDOVER)], env=env, capture_output=True, timeout=60, check=False)

    assert done.returncode == 0, done.stderr.decode()
    said = json.loads(done.stdout)
    (window,) = said["windows"]
    assert window[2:] == list(PROBE)
    assert window[1] != 0
    assert said["frame"] == [64, 32]
    assert said["exit"] == 0
