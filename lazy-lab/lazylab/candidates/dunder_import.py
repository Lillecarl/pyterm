"""
`builtins.__import__` replaced, so every import statement asks first.

No loader and no rewrite: the statement runs as written, and what it
gets back is a proxy. The cost is that the call cannot see the
statement. It does not know the name it binds, so a proxy rebinds by
looking for itself in the namespace; it does not know whether it sits
in a `try`, so the frame decides: only module-level code goes lazy. And
`importlib.import_module` never calls `__import__`, so it stays eager.
"""

from __future__ import annotations

import builtins
import importlib.util
import sys
import types
from typing import TYPE_CHECKING

from .. import proxy

if TYPE_CHECKING:
    from ..policy import Policy

AVAILABLE = True

STATS = {"lazy": 0}


class _Members:
    "What `from target import ...` gets: each fetch a proxy of one member."

    # One slot with an unlikely name, and every other fetch is a member:
    # `from m import site` must not find an attribute of this object.
    __slots__ = ("_lazylab_state",)

    def __init__(self, namespace, target, site):
        object.__setattr__(self, "_lazylab_state", (namespace, target, site))

    def __getattribute__(self, attr):
        namespace, target, site = object.__getattribute__(self, "_lazylab_state")
        return proxy.lazy_from(namespace, None, target, attr, site)


def install(policy: Policy) -> None:
    eager = builtins.__import__

    def lazily(name, globals=None, locals=None, fromlist=(), level=0):
        if globals is None or "*" in (fromlist or ()):
            return eager(name, globals, locals, fromlist, level)
        frame = sys._getframe(1)
        if frame.f_code.co_name != "<module>" or frame.f_globals is not globals:
            return eager(name, globals, locals, fromlist, level)
        importer = globals.get("__name__") or ""
        if importer.partition(".")[0] == "lazylab" or name == "__future__":
            return eager(name, globals, locals, fromlist, level)
        target = importlib.util.resolve_name("." * level + name, globals.get("__package__")) if level else name
        if not policy(importer, target, tuple(fromlist) if fromlist else None):
            return eager(name, globals, locals, fromlist, level)
        if target in sys.modules and not fromlist:
            return eager(name, globals, locals, fromlist, level)
        STATS["lazy"] += 1
        site = "%s:%d" % (frame.f_code.co_filename, frame.f_lineno)
        # So a fetch from outside resolves what it finds, as the AST
        # rewrite's modules do.
        module = sys.modules.get(importer)
        if module is not None and type(module) is types.ModuleType and module.__dict__ is globals:
            module.__class__ = proxy.LazyModuleType
        if fromlist:
            return _Members(globals, target, site)
        # `import a.b` binds `a`, and `import a.b as c` fetches `b` from it.
        return proxy.lazy_mod(globals, None, target, site)

    builtins.__import__ = lazily
