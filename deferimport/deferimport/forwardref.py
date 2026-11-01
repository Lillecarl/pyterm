"""
Before 3.15: a forward reference reads a lazy name resolved, as on 3.15.

3.15 resolves a lazy name where an evaluation reads it. A proxy is a plain
value in a namespace, and a forward reference reads the namespace itself, so
`typing.get_type_hints` gave the proxy, and pydantic called `__new__` on one
(tree_sitter_config's `AnyUrl` field). Before each evaluation, `patch`
resolves the names its code reads, in each namespace it may read them from.

3.14 keeps `ForwardRef` in `annotationlib`, 3.11 to 3.13 in `typing`. Both
are loaded once `deferimport` is: `dataclasses`, which `policy` imports,
imports `annotationlib`.
"""

from __future__ import annotations

import functools
import sys
import typing

from .proxy import LazyProxy

__all__ = ["patch"]

_DONE = "__deferimport_resolves__"


def _resolve(names, namespace) -> None:
    get = getattr(namespace, "get", None)
    if get is None:
        return
    for name in names:
        value = get(name)
        if type(value) is LazyProxy:
            real = value._reify()
            # A copy of the namespace that holds it: the proxy rebinds only
            # its own.
            if isinstance(namespace, dict) and namespace.get(name) is value:
                namespace[name] = real


def _module_dict(name):
    return getattr(sys.modules.get(name) if isinstance(name, str) else None, "__dict__", None)


def _before(ref, globalns, localns, owner) -> None:
    try:
        names = ref.__forward_code__.co_names
    except SyntaxError:
        return  # the evaluation raises it, with its own message
    if not names:
        return
    owner = owner if owner is not None else getattr(ref, "__owner__", None)
    namespaces = (
        globalns,
        localns,
        getattr(ref, "__globals__", None),
        _module_dict(getattr(ref, "__forward_module__", None)),
        _module_dict(getattr(owner, "__module__", None)),
        getattr(owner, "__dict__", None),
        getattr(owner, "__globals__", None),
    )
    for namespace in namespaces:
        if namespace is not None:
            _resolve(names, namespace)


def patch() -> None:
    "Make every forward reference this interpreter evaluates resolve a proxy first."
    if sys.version_info >= (3, 14):
        import annotationlib

        cls = annotationlib.ForwardRef
        if getattr(cls, _DONE, False):
            return
        evaluate = cls.evaluate

        @functools.wraps(evaluate)
        def evaluating(self, /, **kwargs):
            _before(self, kwargs.get("globals"), kwargs.get("locals"), kwargs.get("owner"))
            return evaluate(self, **kwargs)

        cls.evaluate = evaluating
    else:
        cls = typing.ForwardRef
        if getattr(cls, _DONE, False):
            return
        evaluate = cls._evaluate

        @functools.wraps(evaluate)
        def evaluating(self, globalns, localns, *args, **kwargs):
            _before(self, globalns, localns, None)
            return evaluate(self, globalns, localns, *args, **kwargs)

        cls._evaluate = evaluating
    setattr(cls, _DONE, True)
