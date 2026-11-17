"""
A headless Wayland compositor, built on Smithay.

`Compositor` listens for Wayland clients and draws nothing itself: each
window's pixels come back as RGBA, with the rectangles the client said
it changed. The caller owns the event loop.

`RemoteCompositor` has the same methods, for a compositor in a child
process (`pysmithay.host`), whose windows outlive the process that
shows them.
"""

from __future__ import annotations

from pysmithay._native import Compositor, RemoteCompositor, RemoteEncoder, Vp9Encoder

__all__ = ["Compositor", "RemoteCompositor", "RemoteEncoder", "Vp9Encoder"]
