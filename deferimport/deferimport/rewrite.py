"""
Before 3.15: the rewrite of each import the policy picks into a proxy.

`import a.b` becomes `a = __deferimport__.mod("a", "a.b", site)`, and so
on for each spelling; `loads.py` then rewrites the reads of the names
those statements bind, and every flag starts false at the top of the
module.
"""

from __future__ import annotations

import ast
import importlib.util
import sys
from typing import TYPE_CHECKING

from . import hook, loads, proxy, select

if TYPE_CHECKING:
    import types

    from .policy import Policy

__all__ = ["Proxies"]

#: The global the rewritten statements call through.
BINDER = "__deferimport__"


class _Binder:
    "The calls a rewritten module makes, bound to its namespace."

    __slots__ = ("namespace",)

    def __init__(self, namespace: dict):
        self.namespace = namespace

    def from_(self, name, target, attr, site):
        # As 3.15 binds: with the module loaded, `from m import x` takes `x`
        # at once. A plain `import m` stays lazy even then, as there.
        module = sys.modules.get(target)
        if module is not None and not getattr(getattr(module, "__spec__", None), "_initializing", False):
            try:
                value = getattr(module, attr)
            except AttributeError:
                pass
            else:
                self.namespace[proxy.done(name)] = True
                return value
        return proxy.lazy_from(self.namespace, name, target, attr, site)

    def mod(self, name, fullname, site):
        return proxy.lazy_mod(self.namespace, name, fullname, site)

    def mod_as(self, name, fullname, site):
        return proxy.lazy_mod_as(self.namespace, name, fullname, site)


def _force(value):
    if type(value) is proxy.LazyProxy:
        return value._reify()
    return value


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
        _assign(bound, _call("from_", bound, site.target, alias.name, where), node)
        for alias in node.names
        for bound in [alias.asname or alias.name]
    ]


def _flags(tree: ast.Module, names: set[str]) -> None:
    """
    Every flag false at the top, after the docstring and the future
    imports: a lazy import in a branch that never ran leaves its flag
    unset, and the read of it would raise where the original did not.
    """

    def preamble(at: int, node: ast.stmt) -> bool:
        docstring = at == 0 and isinstance(node, ast.Expr) and isinstance(node.value, ast.Constant)
        return docstring or (isinstance(node, ast.ImportFrom) and node.module == "__future__")

    at = 0
    while at < len(tree.body) and preamble(at, tree.body[at]):
        at += 1
    like = tree.body[min(at, len(tree.body) - 1)]
    flags = [_assign(proxy.done(name), ast.Constant(False), like) for name in sorted(names)]
    tree.body[at:at] = [*flags, _assign(proxy.FLAGS, ast.Constant(True), like)]


class _Replace(ast.NodeTransformer):
    def __init__(self, chosen: dict[int, list[ast.stmt]]):
        self.chosen = chosen

    def generic_visit(self, node):
        replacement = self.chosen.get(id(node))
        if replacement is not None:
            return replacement
        return super().generic_visit(node)


class Proxies:
    name = "proxies"
    rewrites = True

    def rewrite(
        self, tree: ast.Module, importer: str, package: str | None, policy: Policy, filename: str, source: bytes
    ) -> int:
        chosen = {
            id(site.node): _replacement(site, filename)
            for site in select.eligible(tree, package)
            if policy(importer, site.target, site.fromlist)
        }
        if not chosen:
            return 0
        _Replace(chosen).visit(tree)
        bound = {statement.targets[0].id for statements in chosen.values() for statement in statements}
        wrapped, unmatched = loads.wrap_reads(tree, importlib.util.decode_source(source), filename, bound)
        _flags(tree, bound)
        hook.STATS["wrapped"] = hook.STATS.get("wrapped", 0) + wrapped
        hook.STATS["unmatched"] = hook.STATS.get("unmatched", 0) + unmatched
        return len(chosen)

    def prepare(self, module: types.ModuleType, lazy: int) -> None:
        if lazy:
            module.__dict__[BINDER] = _Binder(module.__dict__)
            module.__dict__[loads.FORCE] = _force
            proxy.own_class(module)

    def finish(self, module: types.ModuleType, lazy: int) -> None:
        if lazy:
            proxy.keep_class(module)
