from __future__ import annotations

try:
    import missing_mod
except ImportError:
    missing_mod = None


def which():
    return "fallback" if missing_mod is None else "found"
