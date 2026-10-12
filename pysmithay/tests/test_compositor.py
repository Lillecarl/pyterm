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
        for toplevel in {event[1] for event in commits(events)}:
            compositor.frame_done(toplevel, int(time.monotonic() * 1000) & 0xFFFFFFFF)
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


def test_a_window_says_which_connection_its_client_took(compositor, tmp_path):
    first = launch(compositor, sys.executable, str(CLIENT))
    pump(compositor, lambda seen: ("toplevel", 1, 0) in seen)

    before = set(os.listdir(os.environ["XDG_RUNTIME_DIR"]))
    tag, fd = compositor.connect()
    assert tag != 0
    env = dict(os.environ, WAYLAND_SOCKET=str(fd))
    second = subprocess.Popen([sys.executable, str(CLIENT)], env=env, pass_fds=[fd])
    os.close(fd)
    earlier = pump(compositor, lambda seen: ("toplevel", 2, tag) in seen)
    assert set(os.listdir(os.environ["XDG_RUNTIME_DIR"])) == before

    pump(compositor, lambda seen: all(("closed", id) in earlier + seen for id in (1, 2)))
    first.wait(10)
    second.wait(10)


@pytest.mark.parametrize(
    ("scale", "flags", "told"),
    [(1.5, [], "60 40 180"), (2.0, ["--integer"], "45 30 240")],
    ids=["fractional", "integer"],
)
def test_a_scaled_window_lays_out_small_and_draws_dense(compositor, scale, flags, told):
    "The canvas is the pixels asked for, and the window's buffer lands on them one to one."
    client = launch(compositor, sys.executable, str(CLIENT.with_name("scale_client.py")), *flags)
    try:
        pump(compositor, lambda seen: ("toplevel", 1, 0) in seen)
        compositor.configure(1, 90, 60, scale)
        # The first frame at the new size is the clear colour, before the
        # client has drawn into it.
        red = bytes([0xFF, 0x00, 0x00, 0xFF])
        pump(compositor, lambda seen: commits(seen) and compositor.frame(1)[2][-4:] == red)
        assert client.stdout.readline().decode().strip() == told
        width, height, rgba = compositor.frame(1)
        assert (width, height) == (90, 60)
        assert rgba[:4] == bytes([0x33, 0x66, 0x99, 0xFF])
        assert rgba[-8:-4] == bytes([0x33, 0x66, 0x99, 0xFF])
    finally:
        client.kill()
        print(client.communicate()[0].decode(errors="replace"))


def test_a_scale_that_is_not_positive_is_refused(compositor):
    client = launch(compositor, sys.executable, str(CLIENT))
    try:
        pump(compositor, lambda seen: ("toplevel", 1, 0) in seen)
        with pytest.raises(ValueError):
            compositor.configure(1, 90, 60, 0.0)
    finally:
        client.kill()
        client.wait(10)


def test_a_window_draws_no_title_bar_of_its_own(compositor):
    "It asks for client side and is told server side: the pane draws the frame."
    client = launch(compositor, sys.executable, str(CLIENT.with_name("decoration_client.py")))
    pump(compositor, lambda _seen: client.poll() is not None)
    assert client.stdout.read().decode().strip() == "2"


def test_a_window_names_the_pointer_it_wants(compositor):
    "Lillecarl/pymux#650."
    client = launch(compositor, sys.executable, str(CLIENT.with_name("cursor_client.py")))
    try:
        pump(compositor, lambda seen: commits(seen))
        compositor.pointer_motion(1, 5.0, 5.0, 1)
        pump(compositor, lambda seen: ("pointer", 1, "pointer") in seen)
    finally:
        client.kill()
        client.wait(10)


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
