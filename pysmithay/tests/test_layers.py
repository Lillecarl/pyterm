"""
A window composed whole: its subsurfaces and popups land on its frame,
where the protocol puts them, and the pointer reaches each one.
"""

from __future__ import annotations

import select
import sys
from pathlib import Path

from test_compositor import launch, pump

CLIENT = Path(__file__).with_name("layers_client.py")

BLUE = (0x00, 0x00, 0xFF)
GREEN = (0x00, 0xFF, 0x00)
RED = (0xFF, 0x00, 0x00)
YELLOW = (0xFF, 0xFF, 0x00)


def ready(compositor):
    "The layers client, once it has drawn all four surfaces."
    client = launch(compositor, sys.executable, str(CLIENT))
    said = []

    def drew(_seen) -> bool:
        if select.select([client.stdout], [], [], 0)[0]:
            said.append(client.stdout.readline())
        return bool(said)

    # "ready" follows a roundtrip, which the compositor answers in the
    # dispatch that drew the last commit.
    pump(compositor, drew)
    return client


def colour_at(compositor, x, y):
    width, _height, rgba = compositor.frame(1)
    start = (y * width + x) * 4
    return tuple(rgba[start : start + 3])


def test_a_subsurface_lands_at_its_position(compositor):
    client = ready(compositor)
    try:
        assert colour_at(compositor, 4, 4) == GREEN
        assert colour_at(compositor, 11, 11) == GREEN
        assert colour_at(compositor, 12, 12) == BLUE
    finally:
        client.kill()


def test_a_popup_lands_where_its_positioner_says(compositor):
    client = ready(compositor)
    try:
        assert colour_at(compositor, 20, 10) == RED
        assert colour_at(compositor, 29, 15) == RED
        assert colour_at(compositor, 30, 16) == BLUE
    finally:
        client.kill()


def test_a_popup_over_the_edge_slides_back_inside(compositor):
    "Anchored at (60, 28), 10x6 would end at (70, 34): it slides to (54, 26)."
    client = ready(compositor)
    try:
        assert colour_at(compositor, 54, 26) == YELLOW
        assert colour_at(compositor, 63, 31) == YELLOW
        assert colour_at(compositor, 53, 26) == BLUE
    finally:
        client.kill()
