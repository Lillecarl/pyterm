"An import that only works inside the `with` around it."

from __future__ import annotations

import contextlib
import os
import sys

HIDDEN = os.path.join(os.path.dirname(os.path.dirname(__file__)), "hidden")


@contextlib.contextmanager
def on_the_path():
    sys.path.insert(0, HIDDEN)
    try:
        yield
    finally:
        sys.path.remove(HIDDEN)


with on_the_path():
    import hidden_mod


def use():
    return hidden_mod.VALUE
