"""
The compositor against real Wayland clients.

`client.py` draws pixels it knows, so the frame and the damage that come
back can be compared exactly. foot is a real program, which only has to
show up and draw something.
"""

from __future__ import annotations

import os
import select
import subprocess
import sys
import time
from pathlib import Path

import pytest


CLIENT = Path(__file__).with_name("client.py")


def pump(compositor, until, timeout=10.0):
    """
    Run the compositor until `until(events)` holds for every event seen.

    The complaint is built after the deadline, so it names everything
    that did arrive.
    """
    seen = []
    deadline = time.monotonic() + timeout
    while not until(seen):
        left = deadline - time.monotonic()
        if left <= 0:
            pytest.fail("gave up waiting; saw %r" % (seen,))
        select.select(compositor.fds(), [], [], min(left, 0.1))
        events = compositor.dispatch()
        seen.extend(events)
        if any(event[0] == "commit" for event in events):
            compositor.frame_done(int(time.monotonic() * 1000) & 0xFFFFFFFF)
    return seen


def launch(compositor, *command):
    env = dict(os.environ, WAYLAND_DISPLAY=compositor.socket_name)
    return subprocess.Popen(command, env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)


def commits(events):
    return [event for event in events if event[0] == "commit"]


def test_a_client_finds_the_socket(compositor):
    assert compositor.socket_name
    assert (Path(os.environ["XDG_RUNTIME_DIR"]) / compositor.socket_name).exists()


def test_the_first_frame_is_the_buffer_as_rgba(compositor):
    client = launch(compositor, sys.executable, str(CLIENT))
    events = pump(compositor, lambda seen: len(commits(seen)) >= 1)

    assert ("title", 1, "probe") in events
    assert ("app_id", 1, "pysmithay.probe") in events
    assert commits(events)[0] == ("commit", 1, [(0, 0, 64, 32)])
    width, height, rgba = compositor.frame(1)
    assert (width, height) == (64, 32)
    assert rgba == bytes([0x33, 0x66, 0x99, 0xFF]) * (64 * 32)

    pump(compositor, lambda seen: ("closed", 1) in seen)
    client.wait(10)


def test_the_second_frame_names_only_what_changed(compositor):
    client = launch(compositor, sys.executable, str(CLIENT))
    events = pump(compositor, lambda seen: len(commits(seen)) >= 2)

    assert commits(events)[1] == ("commit", 1, [(10, 5, 4, 4)])
    width, _height, rgba = compositor.frame(1)

    def pixel(x, y):
        start = (y * width + x) * 4
        return rgba[start : start + 4]

    assert pixel(10, 5) == bytes([0xFF, 0x00, 0x00, 0xFF])
    assert pixel(13, 8) == bytes([0xFF, 0x00, 0x00, 0xFF])
    assert pixel(14, 8) == bytes([0x33, 0x66, 0x99, 0xFF])

    pump(compositor, lambda seen: ("closed", 1) in seen)
    client.wait(10)
    assert compositor.toplevels() == []


def test_a_window_draws_no_title_bar_of_its_own(compositor):
    "It asks for client side and is told server side: the pane draws the frame."
    client = launch(compositor, sys.executable, str(CLIENT.with_name("decoration_client.py")))
    pump(compositor, lambda _seen: client.poll() is not None)
    assert client.stdout.read().decode().strip() == "2"


def test_a_real_terminal_draws(compositor):
    "foot asks for a size, gets one, and paints something that is not blank."
    foot = launch(compositor, "foot", "--override=main.font=DejaVu Sans Mono:size=8", "sh", "-c", "sleep 30")
    try:
        events = pump(compositor, lambda seen: any(event[0] == "commit" and event[2] for event in seen), 20.0)
        (toplevel,) = compositor.toplevels()
        width, height, rgba = compositor.frame(toplevel)
        assert width > 0 and height > 0
        assert len(set(rgba[i : i + 4] for i in range(0, len(rgba), 4))) > 1, "a frame of one colour"
        assert any(event[0] == "app_id" and event[2] == "foot" for event in events)
    finally:
        foot.kill()
        output = foot.communicate()[0].decode(errors="replace")
        print(output)
