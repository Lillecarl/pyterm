"A module that gives itself a class of its own while it loads."

from __future__ import annotations

import sys
import types

import heavy


class Module(types.ModuleType):
    pass


sys.modules[__name__].__class__ = Module


def use():
    return heavy.Thing()
