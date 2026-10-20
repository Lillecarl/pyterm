"""
3.14: a lazy `import a.b` still makes `a.b` reachable, as on 3.15.

Eagerly, `import a.b` leaves `b` as an attribute of `a`, and code
elsewhere reads `a.b` trusting that somebody imported it: pymux reads
`anyio.to_thread` that way. A proxy imports nothing until used, so that
attribute is missing and the read fails -- 299 of pymux's tests did.
3.15 keeps such a submodule pending (`sys.lazy_modules`), and a read of
it imports it.

The same here: a lazy import records the submodule as pending on its
parent, and the parent package gets a class of its own with a
`__getattr__`. That runs only when a fetch misses, so a fetch that hits
costs nothing more. A parent not loaded yet gets its class from a finder
that waits for it.
"""

from __future__ import annotations

import importlib
import sys
import types
from collections import defaultdict

__all__ = ["PENDING", "register", "register_dotted"]

#: Submodules a lazy import names and nothing imported yet, by parent.
PENDING: dict[str, set[str]] = defaultdict(set)


def _getattr(module, name):
    parent = module.__name__
    pending = PENDING.get(parent)
    if pending and name in pending:
        pending.discard(name)
        fullname = "%s.%s" % (parent, name)
        try:
            importlib.import_module(fullname)
        except ModuleNotFoundError as exc:
            if exc.name != fullname:
                raise
        else:
            return module.__dict__[name]
    raise AttributeError("module %r has no attribute %r" % (parent, name))


def _attach(module: types.ModuleType) -> None:
    cls = type(module)
    # Only a package has submodules; and a class looked up on the type
    # never reaches the module's own `__getattr__`.
    if getattr(cls, "_deferimport_pending", False) or "__path__" not in module.__dict__:
        return
    module.__class__ = type("PendingSubmodules", (cls,), {"__getattr__": _getattr, "_deferimport_pending": True})


class _Attach:
    "A loader that gives the module its class once it has run."

    def __init__(self, loader):
        self._loader = loader

    def create_module(self, spec):
        return self._loader.create_module(spec)

    def exec_module(self, module):
        self._loader.exec_module(module)
        _attach(module)

    def __getattr__(self, name):
        return getattr(self._loader, name)


class _Waiter:
    "Finds nothing itself: hands a parent with pending submodules to `_Attach`."

    _deferimport = True

    def find_spec(self, fullname, path, target=None):
        if fullname not in PENDING:
            return None
        for finder in sys.meta_path[sys.meta_path.index(self) + 1 :]:
            find = getattr(finder, "find_spec", None)
            spec = find(fullname, path, target) if find is not None else None
            if spec is not None:
                if spec.loader is not None and hasattr(spec.loader, "exec_module"):
                    spec.loader = _Attach(spec.loader)
                return spec
        return None


_WAITER = _Waiter()


def register(parent: str, name: str) -> None:
    "Record `parent.name` as pending, and make `parent` resolve it."
    PENDING[parent].add(name)
    module = sys.modules.get(parent)
    if module is not None:
        _attach(module)
    elif _WAITER not in sys.meta_path:
        sys.meta_path.insert(0, _WAITER)


def register_dotted(fullname: str) -> None:
    "Every link of `import a.b.c`: `b` on `a`, and `c` on `a.b`."
    parts = fullname.split(".")
    for at in range(1, len(parts)):
        register(".".join(parts[:at]), parts[at])
