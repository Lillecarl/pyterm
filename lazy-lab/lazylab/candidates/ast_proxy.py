"""
The AST rewrite into proxies, for an interpreter with no lazy imports.

Each import the policy picks becomes an assignment of a `LazyProxy`, the
one the `lazy-imports` branch's shim builds from the `lazy` keyword.
Here the policy picks, and the source stays plain Python.

Two variants. `ast-proxy` keeps a rewritten module on `LazyModuleType`
for good, as the shim does. `ast-proxy-restore` puts it back on
`types.ModuleType` once its last proxy resolves, so an attribute fetch
from outside stops paying a `__getattribute__` written in Python.
"""

from __future__ import annotations

import ast
from typing import TYPE_CHECKING

from .. import hook, proxy, select

if TYPE_CHECKING:
    import types

    from ..policy import Policy

AVAILABLE = True

#: The global the rewritten statements call through.
BINDER = "__lazylab__"


class _Binder:
    "The calls a rewritten module makes, bound to its namespace."

    __slots__ = ("namespace",)

    def __init__(self, namespace: dict):
        self.namespace = namespace

    def mod(self, name, fullname, site):
        return proxy.lazy_mod(self.namespace, name, fullname, site)

    def mod_as(self, name, fullname, site):
        return proxy.lazy_mod_as(self.namespace, name, fullname, site)

    def from_(self, name, target, attr, site):
        return proxy.lazy_from(self.namespace, name, target, attr, site)


def _call(method: str, *args) -> ast.expr:
    return ast.Call(
        func=ast.Attribute(value=ast.Name(BINDER, ast.Load()), attr=method, ctx=ast.Load()),
        args=[ast.Constant(arg) for arg in args],
        keywords=[],
    )


def _assign(name: str, value: ast.expr, like: ast.stmt) -> ast.stmt:
    return ast.copy_location(ast.Assign(targets=[ast.Name(name, ast.Store())], value=value), like)


def _replacement(site: select.Site, filename: str) -> list[ast.stmt]:
    node = site.node
    where = "%s:%d" % (filename, node.lineno)
    if isinstance(node, ast.Import):
        alias = node.names[0]
        if alias.asname:
            return [_assign(alias.asname, _call("mod_as", alias.asname, alias.name, where), node)]
        top = alias.name.partition(".")[0]
        method = "mod" if "." in alias.name else "mod_as"
        return [_assign(top, _call(method, top, alias.name, where), node)]
    return [
        _assign(
            alias.asname or alias.name, _call("from_", alias.asname or alias.name, site.target, alias.name, where), node
        )
        for alias in node.names
    ]


class _Replace(ast.NodeTransformer):
    def __init__(self, chosen: dict[int, list[ast.stmt]]):
        self.chosen = chosen

    def generic_visit(self, node):
        replacement = self.chosen.get(id(node))
        if replacement is not None:
            return replacement
        return super().generic_visit(node)


class Proxy:
    def __init__(self, restore: bool):
        self.restore = restore
        self.name = "ast-proxy-restore" if restore else "ast-proxy"

    def rewrite(self, tree: ast.Module, importer: str, package: str | None, policy: Policy, filename: str) -> int:
        chosen = {
            id(site.node): _replacement(site, filename)
            for site in select.eligible(tree, package)
            if policy(importer, site.target, site.fromlist)
        }
        if chosen:
            _Replace(chosen).visit(tree)
        return len(chosen)

    def prepare(self, module: types.ModuleType, lazy: int) -> None:
        if lazy:
            module.__dict__[BINDER] = _Binder(module.__dict__)
            module.__class__ = proxy.LazyModuleType


def install(policy: Policy, *, restore: bool = False) -> None:
    proxy.RESTORE = restore
    hook.install(Proxy(restore), policy)
