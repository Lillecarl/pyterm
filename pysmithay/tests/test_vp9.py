"""
A window as a VP9 stream: a keyframe first, then only the blocks under
the damage. ffmpeg decodes what the encoder made, and the pixels have to
come back close to the ones the probe client drew: the encoding is lossy.
Lillecarl/pymux#639.
"""

from __future__ import annotations

import asyncio
import shutil
import struct
import subprocess
import sys

from test_compositor import CLIENT, commits, launch, pump

from pysmithay import Vp9Encoder

WIDTH, HEIGHT = 64, 32
#: The probe's fill and square, as RGB.
FILL = bytes([0x33, 0x66, 0x99])
RED = bytes([0xFF, 0, 0])


def frame(compositor, encoder):
    async def awaited():
        return await compositor.vp9_frame(1, encoder)

    return asyncio.run(awaited())


def decoded(packets: list[bytes]) -> list[bytes]:
    "Every frame of the stream as RGB, decoded by ffmpeg."
    header = b"DKIF" + struct.pack("<HH4sHHIIII", 0, 32, b"VP90", WIDTH, HEIGHT, 30, 1, len(packets), 0)
    ivf = header + b"".join(struct.pack("<IQ", len(packet), at) + packet for at, packet in enumerate(packets))
    ffmpeg = shutil.which("ffmpeg")
    assert ffmpeg, "the check puts ffmpeg on PATH"
    raw = subprocess.run(
        [
            ffmpeg,
            "-hide_banner",
            "-loglevel",
            "error",
            "-f",
            "ivf",
            "-i",
            "-",
            "-f",
            "rawvideo",
            "-pix_fmt",
            "rgb24",
            "-",
        ],
        input=ivf,
        capture_output=True,
        check=True,
    ).stdout
    size = WIDTH * HEIGHT * 3
    return [raw[at : at + size] for at in range(0, len(raw), size)]


def pixel(rgb: bytes, x: int, y: int) -> bytes:
    at = (y * WIDTH + x) * 3
    return rgb[at : at + 3]


def assert_near(got: bytes, want: bytes) -> None:
    assert max(abs(a - b) for a, b in zip(got, want, strict=True)) <= 8, (got, want)


def test_the_stream_starts_with_a_keyframe_and_then_sends_the_damaged_blocks(compositor):
    client = launch(compositor, sys.executable, str(CLIENT))
    encoder = Vp9Encoder()
    pump(compositor, lambda seen: len(commits(seen)) >= 1)
    serial, keyframe, width, height, first, rects = frame(compositor, encoder)
    assert (serial, keyframe, width, height, rects) == (1, True, WIDTH, HEIGHT, [(0, 0, WIDTH, HEIGHT)])

    pump(compositor, lambda seen: len(commits(seen)) >= 1)
    serial, keyframe, _width, _height, second, rects = frame(compositor, encoder)
    # The 4x4 square at (10, 5) lies in the block at the origin.
    assert (serial, keyframe, rects) == (2, False, [(0, 0, 16, 16)])

    before, after = decoded([first, second])
    assert_near(pixel(before, 11, 6), FILL)
    assert_near(pixel(after, 11, 6), RED)
    assert_near(pixel(after, 40, 20), FILL)
    client.kill()


def test_a_reader_up_to_date_gets_no_data(compositor):
    client = launch(compositor, sys.executable, str(CLIENT))
    pump(compositor, lambda seen: len(commits(seen)) >= 2)
    encoder = Vp9Encoder()
    frame(compositor, encoder)
    assert frame(compositor, encoder) == (2, False, WIDTH, HEIGHT, b"", [])
    client.kill()


def test_every_reader_has_a_stream_of_its_own(compositor):
    "A second encoder starts with a keyframe of its own, whatever the first sent."
    client = launch(compositor, sys.executable, str(CLIENT))
    pump(compositor, lambda seen: len(commits(seen)) >= 2)
    frame(compositor, Vp9Encoder())
    _serial, keyframe, *_rest = frame(compositor, Vp9Encoder())
    assert keyframe
    client.kill()
