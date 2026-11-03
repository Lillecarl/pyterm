"A fallback on an eager import of a module whose own import is missing."

from __future__ import annotations

try:
    from app.missing import use_module
except ImportError:
    use_module = None


def which():
    return "fallback" if use_module is None else "found"
