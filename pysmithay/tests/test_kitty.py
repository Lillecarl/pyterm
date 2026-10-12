"""
A window as kitty graphics commands: the whole frame first, then only
what the client damaged, as edits of the root frame.
"""

from __future__ import annotations

import base64
import re
import sys
import zlib

from test_compositor import CLIENT, commits, launch, pump

#: One graphics command: its keys and its payload.
COMMAND = re.compile(r"\x1b_G([^;]*);([^\x1b]*)\x1b\\")


def commands(text: str) -> list[tuple[dict[str, str], bytes]]:
    """
    Each transmission in `text`, with its chunks joined: the keys of the
    first chunk, and the decompressed pixels.
    """
    joined: list[tuple[dict[str, str], str]] = []
    for keys, payload in COMMAND.findall(text):
        parsed = dict(pair.split("=", 1) for pair in keys.split(","))
        if joined and set(parsed) == {"m"} and joined[-1][0].get("_more") == "1":
            joined[-1][0]["_more"] = parsed["m"]
            joined[-1] = (joined[-1][0], joined[-1][1] + payload)
        else:
            parsed["_more"] = parsed["m"]
            joined.append((parsed, payload))
    return [(keys, zlib.decompress(base64.b64decode(payload))) for keys, payload in joined]


def probe(compositor):
    "The probe client drawn twice: its full frame, then a 4x4 red square."
    client = launch(compositor, sys.executable, str(CLIENT))
    pump(compositor, lambda seen: len(commits(seen)) >= 2)
    return client


def test_the_first_update_sends_the_whole_frame(compositor):
    client = probe(compositor)
    serial, text, whole = compositor.kitty_update(1, 7)

    assert whole
    assert serial == 2
    ((keys, pixels),) = commands(text)
    # The canvas is opaque, so the frame goes as RGB.
    assert (keys["a"], keys["i"], keys["s"], keys["v"], keys["f"]) == ("t", "7", "64", "32", "24")
    assert len(pixels) == 64 * 32 * 3
    assert pixels[(5 * 64 + 10) * 3 : (5 * 64 + 10) * 3 + 3] == bytes([0xFF, 0, 0])
    client.kill()


def test_a_reader_one_frame_behind_gets_the_damage_only(compositor):
    client = probe(compositor)
    serial, text, whole = compositor.kitty_update(1, 7, since=1)

    assert not whole
    assert serial == 2
    ((keys, pixels),) = commands(text)
    assert (keys["a"], keys["r"], keys["x"], keys["y"], keys["s"], keys["v"], keys["X"]) == (
        "f",
        "1",
        "10",
        "5",
        "4",
        "4",
        "1",
    )
    assert pixels == bytes([0xFF, 0, 0]) * 16
    client.kill()


def test_a_reader_up_to_date_gets_nothing(compositor):
    client = probe(compositor)
    assert compositor.kitty_update(1, 7, since=2) == (2, "", False)
    client.kill()


def test_a_reader_from_the_future_gets_the_whole_frame(compositor):
    "A serial it cannot place, as after the window was replaced."
    client = probe(compositor)
    _serial, _text, whole = compositor.kitty_update(1, 7, since=99)
    assert whole
    client.kill()
