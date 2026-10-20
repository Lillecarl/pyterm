"""
The import statements a rewrite may make lazy: the ones 3.15 picks.

Measured on 3.15.0 with `-X lazy_imports=all`: an import at module
scope goes lazy, also nested in `if`, `with`, `for`, `while` and
`match`. One inside `try` (any part of it), a class body or a function
stays eager, and so do star imports and `from __future__`. Both
mechanisms select this one set, and the probe `positions` holds it
against the interpreter's own.
"""

from __future__ import annotations

import ast
import importlib.util
from dataclasses import dataclass

__all__ = ["Site", "eligible", "split_imports"]

#: Statements whose bodies are still module scope.
_THROUGH = (ast.If, ast.With, ast.AsyncWith, ast.For, ast.AsyncFor, ast.While, ast.Match)


@dataclass(frozen=True)
class Site:
    node: ast.Import | ast.ImportFrom
    #: The absolute name of the module the statement imports.
    target: str
    #: `None` for `import x`, the imported names for `from x import ...`.
    fromlist: tuple[str, ...] | None


def _children(node: ast.AST):
    for name in ("body", "orelse"):
        yield from getattr(node, name, ())
    for case in getattr(node, "cases", ()):
        yield from case.body


def _walk(statements):
    for node in statements:
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            yield node
        elif isinstance(node, _THROUGH):
            yield from _walk(_children(node))


class _Split(ast.NodeTransformer):
    def visit_Import(self, node: ast.Import):
        if len(node.names) == 1:
            return node
        return [ast.copy_location(ast.Import(names=[alias]), node) for alias in node.names]


def split_imports(tree: ast.Module) -> ast.Module:
    """
    `import a, b` as two statements, so a policy decides each name alone.
    The two spellings bind the same names in the same order.
    """
    return _Split().visit(tree)


def eligible(tree: ast.Module, package: str | None) -> list[Site]:
    """
    Every import in `tree` a lazy rewrite may take, with its resolved
    target. `tree` has been through `split_imports`.
    """
    sites = []
    for node in _walk(tree.body):
        if isinstance(node, ast.Import):
            sites.append(Site(node, node.names[0].name, None))
            continue
        if node.module == "__future__" or any(alias.name == "*" for alias in node.names):
            continue
        relative = "." * node.level + (node.module or "")
        if node.level:
            # One that reaches past the top fails as written, eagerly.
            try:
                target = importlib.util.resolve_name(relative, package)
            except ImportError, ValueError:
                continue
        else:
            target = relative
        sites.append(Site(node, target, tuple(alias.name for alias in node.names)))
    return sites
