"""
A headless Wayland compositor, built on Smithay.

`Compositor` listens for Wayland clients and draws nothing itself: each
window's pixels come back as RGBA, with the rectangles the client said
it changed. The caller owns the event loop.
"""

from __future__ import annotations

from pysmithay._native import Compositor

__all__ = ["Compositor"]
