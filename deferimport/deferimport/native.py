"""
3.15: the rewrite sets `is_lazy` on each import the policy picks.

That compiles to the bytecode `lazy import` compiles to: the name binds a
lazy object, and its first load imports and rebinds, in C. Nothing of
this package runs after the import, and the frame cost measured +0.0%.
`sys.set_lazy_imports_filter` gives the same semantics with no rewrite,
but calls the policy in Python on every import, every start: up to +68%
instructions on an import workload. Here the policy runs once per module,
and the cache keeps its answer.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from . import select

if TYPE_CHECKING:
    import ast
    import types

    from .policy import Policy

__all__ = ["Native"]


class Native:
    name = "native"

    def rewrite(
        self, tree: ast.Module, importer: str, package: str | None, policy: Policy, filename: str, source: bytes
    ) -> int:
        lazy = 0
        for site in select.eligible(tree, package):
            if policy(importer, site.target, site.fromlist):
                site.node.is_lazy = 1
                lazy += 1
        return lazy

    def prepare(self, module: types.ModuleType, lazy: int) -> None:
        pass

    def finish(self, module: types.ModuleType, lazy: int) -> None:
        pass
