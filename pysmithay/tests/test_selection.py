"""
The clipboard, against wl-copy and wl-paste.

Both reach it through the data-control protocols, the way a clipboard
manager does, so no window of theirs ever needs focus.
"""

from __future__ import annotations

import os
import select
import subprocess
import sys
import threading
import time
from pathlib import Path

import pytest

from pysmithay import Compositor

TEXT = "text/plain;charset=utf-8"
PASTE_CLIENT = Path(__file__).with_name("paste_client.py")


def environment(compositor):
    return dict(os.environ, WAYLAND_DISPLAY=compositor.socket_name)


def pump(compositor, until, timeout=10.0):
    "Dispatch until `until(seen)` holds; the complaint names what came."
    seen = []
    deadline = time.monotonic() + timeout
    while not until(seen):
        left = deadline - time.monotonic()
        if left <= 0:
            pytest.fail("gave up waiting; saw %r" % (seen,))
        select.select(compositor.fds(), [], [], min(left, 0.05))
        seen.extend(compositor.dispatch())
    return seen


def read_while_pumping(compositor, fd):
    "The holder writes only while the compositor runs, so read on a thread."
    chunks = []
    done = threading.Event()

    def read():
        with os.fdopen(fd, "rb") as pipe:
            chunks.append(pipe.read())
        done.set()

    threading.Thread(target=read, daemon=True).start()
    pump(compositor, lambda _seen: done.is_set())
    return b"".join(chunks)


def copy(compositor, text, *flags):
    "wl-copy, kept in the foreground so the test owns its lifetime."
    return subprocess.Popen(
        ["wl-copy", "--foreground", *flags, text],
        env=environment(compositor),
        stderr=subprocess.PIPE,
    )


def paste(compositor, *flags):
    "Run wl-paste to the end while the compositor serves it."
    process = subprocess.Popen(
        ["wl-paste", "--no-newline", *flags],
        env=environment(compositor),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    out = []
    reader = threading.Thread(target=lambda: out.append(process.communicate()), daemon=True)
    reader.start()
    pump(compositor, lambda _seen: not reader.is_alive())
    stdout, stderr = out[0]
    return process.returncode, stdout, stderr


@pytest.mark.parametrize(("target", "flags"), [("clipboard", ()), ("primary", ("--primary",))])
def test_what_a_client_copies_reaches_python(compositor, target, flags):
    holder = copy(compositor, "copied by wl-copy", *flags)
    try:
        events = pump(
            compositor,
            lambda seen: any(event[0] == "selection" and event[1] == target and event[2] for event in seen),
        )
        (offered,) = [event[2] for event in events if event[0] == "selection" and event[1] == target]
        assert TEXT in offered

        fd = compositor.request_selection(target, TEXT)
        assert read_while_pumping(compositor, fd) == b"copied by wl-copy"
    finally:
        holder.kill()
        holder.wait()


@pytest.mark.parametrize(("target", "flags"), [("clipboard", ()), ("primary", ("--primary",))])
def test_what_python_holds_reaches_a_client(compositor, target, flags):
    compositor.set_selection(target, {TEXT: b"held by pymux", "text/plain": b"held by pymux"})

    code, stdout, stderr = paste(compositor, *flags)

    assert code == 0, stderr
    assert stdout == b"held by pymux"


def test_python_answers_a_selection_held_with_none(compositor):
    "The paste waits for Python, which writes when it has the bytes."
    compositor.set_selection("clipboard", {TEXT: None})
    process = subprocess.Popen(
        ["wl-paste", "--no-newline"],
        env=environment(compositor),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    try:
        events = pump(compositor, lambda seen: any(event[0] == "send" for event in seen))
        (send,) = [event for event in events if event[0] == "send"]
        _, target, mime_type, fd = send
        assert (target, mime_type) == ("clipboard", TEXT)
        os.write(fd, b"answered late")
        os.close(fd)
        pump(compositor, lambda _seen: process.poll() is not None)
        stdout, stderr = process.communicate()
        assert process.returncode == 0, stderr
        assert stdout == b"answered late"
    finally:
        if process.poll() is None:
            process.kill()


def test_the_window_with_the_keyboard_is_offered_the_clipboard(compositor):
    "A window pastes what wl-copy copied, as Firefox in a pane does. Lillecarl/pymux#708."
    holder = copy(compositor, "copied beside the window")
    window = subprocess.Popen(
        [sys.executable, "-X", "faulthandler", str(PASTE_CLIENT)],
        env=environment(compositor),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    try:
        events = pump(compositor, lambda seen: any(event[0] == "toplevel" for event in seen))
        (toplevel,) = [event[1] for event in events if event[0] == "toplevel"]
        compositor.focus(toplevel)
        pump(compositor, lambda _seen: window.poll() is not None)
        stdout, stderr = window.communicate()
        assert window.returncode == 0, stderr
        assert stdout == b"copied beside the window"
    finally:
        for process in (window, holder):
            if process.poll() is None:
                process.kill()
            process.wait()


def test_a_large_selection_does_not_stall_the_compositor(compositor):
    "More than a pipe holds, so the write cannot be on the dispatch thread."
    big = b"x" * (1 << 20)
    compositor.set_selection("clipboard", {TEXT: big})

    code, stdout, stderr = paste(compositor)

    assert code == 0, stderr
    assert stdout == big


def test_clearing_leaves_nothing_to_paste(compositor):
    compositor.set_selection("clipboard", {TEXT: b"soon gone"})
    compositor.clear_selection("clipboard")

    code, stdout, _stderr = paste(compositor)

    assert code != 0
    assert stdout == b""


def test_a_selection_has_two_names_only(compositor):
    with pytest.raises(ValueError, match="clipboard"):
        compositor.set_selection("secondary", {TEXT: b""})


def test_an_absolute_socket_path(tmp_path):
    path = str(tmp_path / "pymux-wayland")
    compositor = Compositor(path)

    assert compositor.socket_name == path
    compositor.set_selection("clipboard", {TEXT: b"by path"})
    code, stdout, stderr = paste(compositor)
    assert code == 0, stderr
    assert stdout == b"by path"
