"""
The AST rewrite into 3.15's own lazy imports.

It sets `is_lazy` on each import the policy picks, which compiles to the
same bytecode `lazy import` does: the name binds a `lazy_import` object,
and the first load of it imports and rebinds, in C. No proxy, no module
class, and nothing left to pay once the name resolves. 3.15 only.
"""

from __future__ import annotations

import sys
from typing import TYPE_CHECKING

from .. import hook, select

if TYPE_CHECKING:
    import ast
    import types

    from ..policy import Policy

AVAILABLE = sys.version_info >= (3, 15)


class Native:
    name = "ast-native"

    def rewrite(self, tree: ast.Module, importer: str, package: str | None, policy: Policy, filename: str) -> int:
        lazy = 0
        for site in select.eligible(tree, package):
            if policy(importer, site.target, site.fromlist):
                site.node.is_lazy = 1
                lazy += 1
        return lazy

    def prepare(self, module: types.ModuleType, lazy: int) -> None:
        pass


def install(policy: Policy) -> None:
    hook.install(Native(), policy)
