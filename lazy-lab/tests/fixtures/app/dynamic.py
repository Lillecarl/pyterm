"A module with a lazy import and a PEP 562 `__getattr__`, as ptyhost has."

from __future__ import annotations

import heavy


def __getattr__(name):
    if name == "LATE":
        return "late"
    raise AttributeError(name)


def use():
    return heavy.Thing()
