"""
3.15: no rewrite. The loader sets `__lazy_modules__` before the module
runs, to an object that asks the policy.

3.15 tests `abs_name in __lazy_modules__` at each module-level import
outside a `try`, and makes the import lazy when it is: the name binds a
lazy object, and its first load imports and rebinds, in C. The module
compiles from the bytecode its installer wrote, so a first start costs
what every start costs. Setting `is_lazy` in a rewrite gives the same
semantics two points cheaper warm, and three times eager's start cold,
when every module is parsed and compiled. pyterm's `lazy-lab/` measured
both; `README.md` names the commit.

The test sees the absolute target, never the fromlist. A module that
assigns its own `__lazy_modules__` keeps its own.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from . import hook

if TYPE_CHECKING:
    import ast
    import types

    from .policy import Policy

__all__ = ["Native"]


class _Asks:
    "A `__lazy_modules__` that asks the policy for each import."

    __slots__ = ("importer", "policy")

    def __init__(self, importer: str, policy: Policy):
        self.importer = importer
        self.policy = policy

    def __contains__(self, target: str) -> bool:
        lazy = self.policy(self.importer, target)
        hook.STATS["lazy"] += lazy
        return lazy


class Native:
    name = "native"
    rewrites = False

    def __init__(self, policy: Policy):
        self.policy = policy

    def rewrite(
        self, tree: ast.Module, importer: str, package: str | None, policy: Policy, filename: str, source: bytes
    ) -> int:
        return 0

    def prepare(self, module: types.ModuleType, lazy: int) -> None:
        module.__dict__["__lazy_modules__"] = _Asks(module.__name__, self.policy)

    def finish(self, module: types.ModuleType, lazy: int) -> None:
        pass
