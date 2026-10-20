"""
3.15's global mode with the policy as its filter, and no rewrite at all.

`sys.set_lazy_imports("all")` makes every module-scope import lazy, in
every module, and `sys.set_lazy_imports_filter` takes the policy as it
is. This is the control for `ast-native`: the same bytecode path, picked
by the interpreter instead of by a loader.
"""

from __future__ import annotations

import sys
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ..policy import Policy

AVAILABLE = sys.version_info >= (3, 15)

#: Imports the filter passed, for the same reason `hook.STATS` exists.
STATS = {"lazy": 0}


def install(policy: Policy) -> None:
    def chosen(importer: str, target: str, fromlist) -> bool:
        if importer.partition(".")[0] == "lazylab":
            return False
        lazy = policy(importer, target, tuple(fromlist) if fromlist else None)
        STATS["lazy"] += lazy
        return lazy

    sys.set_lazy_imports_filter(chosen)
    sys.set_lazy_imports("all")
