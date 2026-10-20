"""
3.15's `__lazy_modules__`, set by the loader before the module runs.

No rewrite: the loader takes the bytecode a `SourceFileLoader` takes,
from the store's `__pycache__`. 3.15 checks `abs_name in
__lazy_modules__` at each module-level import that is not in a `try`,
in C, so the container decides the cost:

- `lazy-modules`: a frozenset of the targets the policy picks, read off
  the module's own `IMPORT_NAME` instructions. A C lookup per import.
- `lazy-modules-contains`: an object whose `__contains__` asks the
  policy. A Python call per import, like `native-filter`.

The check sees the absolute target only, never the fromlist: a policy
that tells `import m` from `from m import x` cannot be said here. A
target the policy refuses at any site stays eager at every site. A
module that assigns its own `__lazy_modules__` replaces this one.
"""

from __future__ import annotations

import dis
import importlib.machinery
import importlib.util
import sys
from typing import TYPE_CHECKING, override

from .. import hook

if TYPE_CHECKING:
    import types

    from ..policy import Policy

AVAILABLE = sys.version_info >= (3, 15)

#: `IMPORT_NAME`'s low bits: 1 is the `lazy` keyword, 2 forces eager.
_FORCED_EAGER = 2

STATS = {"lazy": 0}


def targets(code: types.CodeType, importer: str, package: str | None, policy: Policy) -> tuple[frozenset[str], int]:
    "The absolute targets `policy` picks at `code`'s own imports, and how many sites that makes lazy."
    picked: dict[str, list[bool]] = {}
    loaded: list[object] = []
    for instruction in dis.get_instructions(code):
        if instruction.opname != "IMPORT_NAME":
            loaded.append(instruction.argval)
            continue
        level, fromlist = loaded[-2], loaded[-1]
        if instruction.arg & _FORCED_EAGER or not isinstance(level, int):
            continue
        try:
            target = importlib.util.resolve_name("." * level + instruction.argval, package)
        except ImportError:
            continue
        chosen = policy(importer, target, tuple(fromlist) if fromlist else None)
        picked.setdefault(target, []).append(chosen)
    lazy = frozenset(target for target, votes in picked.items() if all(votes))
    return lazy, sum(len(picked[target]) for target in lazy)


class _Asks:
    "A `__lazy_modules__` that asks the policy at each import."

    __slots__ = ("importer", "policy")

    def __init__(self, importer: str, policy: Policy):
        self.importer = importer
        self.policy = policy

    def __contains__(self, target: str) -> bool:
        lazy = self.policy(self.importer, target)
        STATS["lazy"] += lazy
        return lazy


class _Loader(importlib.machinery.SourceFileLoader):
    def __init__(self, fullname: str, path: str, finder: hook.RewriteFinder):
        super().__init__(fullname, path)
        self._finder = finder

    @override
    def exec_module(self, module):
        code = self.get_code(module.__name__)
        name = module.__name__
        if self._finder.transform.name == "lazy-modules":
            package = name if self.is_package(name) else name.rpartition(".")[0]
            lazy, count = targets(code, name, package or None, self._finder.policy)
            STATS["lazy"] += count
        else:
            lazy = _Asks(name, self._finder.policy)
        module.__dict__["__lazy_modules__"] = lazy
        exec(code, module.__dict__)


class _Finder(hook.RewriteFinder):
    loader = _Loader


class LazyModules:
    def __init__(self, name: str):
        self.name = name


def install(policy: Policy, *, contains: bool = False) -> None:
    hook.install(LazyModules("lazy-modules-contains" if contains else "lazy-modules"), policy, _Finder)
