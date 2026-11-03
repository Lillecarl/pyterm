"""
Before 3.15: a forward reference, and an annotation that
`get_annotations(eval_str=True)` evaluates, read a lazy name resolved, as on
3.15.

3.15 resolves a lazy name where an evaluation reads it. A proxy is a plain
value in a namespace, and a forward reference reads the namespace itself, so
`typing.get_type_hints` gave the proxy, and pydantic called `__new__` on one
(tree_sitter_config's `AnyUrl` field). Before each evaluation, `patch`
resolves the names its code reads, in each namespace it may read them from.
`get_annotations` calls `eval` itself and builds no `ForwardRef`, so it gets
the same step of its own.

3.14 keeps `ForwardRef` in `annotationlib`, 3.11 to 3.13 in `typing`. Both
are loaded once `deferimport` is: `dataclasses`, which `policy` imports,
imports `annotationlib`.
"""

from __future__ import annotations

import contextlib
import functools
import sys
import types
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


def _namespaces_of(obj, globalns, localns):
    "Where `get_annotations` evaluates the annotations of `obj`."
    found = [globalns, localns]
    if isinstance(obj, type):
        found += [_module_dict(getattr(obj, "__module__", None)), getattr(obj, "__dict__", None)]
    elif isinstance(obj, types.ModuleType):
        found.append(obj.__dict__)
    else:
        unwrapped = obj
        while True:
            if hasattr(unwrapped, "__wrapped__"):
                unwrapped = unwrapped.__wrapped__
            elif isinstance(unwrapped, functools.partial):
                unwrapped = unwrapped.func
            else:
                break
        found.append(getattr(unwrapped, "__globals__", None))
    return [namespace for namespace in found if namespace is not None]


def _names_in(annotations) -> list[str]:
    names: list[str] = []
    for value in annotations.values():
        if isinstance(value, str):
            # A bad one raises in the evaluation, with its own message.
            with contextlib.suppress(SyntaxError):
                names += compile(value, "<annotation>", "eval").co_names
    return names


def _patch_get_annotations(module) -> None:
    get_annotations = module.get_annotations
    if getattr(get_annotations, _DONE, False):
        return

    @functools.wraps(get_annotations)
    def getting(obj, *, globals=None, locals=None, eval_str=False, **kwargs):
        if eval_str:
            names = _names_in(get_annotations(obj, globals=globals, locals=locals, **kwargs))
            if names:
                for namespace in _namespaces_of(obj, globals, locals):
                    _resolve(names, namespace)
        return get_annotations(obj, globals=globals, locals=locals, eval_str=eval_str, **kwargs)

    setattr(getting, _DONE, True)
    module.get_annotations = getting


def patch() -> None:
    "Make every forward reference this interpreter evaluates resolve a proxy first."
    import inspect

    if sys.version_info >= (3, 14):
        import annotationlib

        _patch_get_annotations(annotationlib)
    _patch_get_annotations(inspect)
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
