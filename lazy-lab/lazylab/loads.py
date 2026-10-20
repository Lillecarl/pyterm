"""
Resolve a lazy global where it is read bare, the way 3.15's
`LOAD_GLOBAL` does, for the proxy rewrite on 3.14.

A proxy resolves itself when it is called or an attribute is fetched,
and then rebinds the global. Any other read hands the proxy itself to
whoever reads it, and C code that checks a type refuses it: `ord()` on
a lazy string constant, `except` on a lazy class,
`Mapping.register(lazy_class)`. So every other read of a lazily bound
global, `X` in `ord(X)`, becomes `__lazylab_force__(X)`.

`symtable` says which reads are of the global. Measured on 3.14: list,
set and dict comprehensions have no table of their own (PEP 709), a
generator expression, a function, a lambda and a class each do, and an
annotation scope sits beside them as `__annotate__`. Annotations are
never rewritten. A scope whose table cannot be found is left alone: a
leak there is possible, a wrong rewrite is not.
"""

from __future__ import annotations

import ast
import symtable

__all__ = ["FORCE", "wrap_bare_loads"]

#: The global a rewritten read calls.
FORCE = "__lazylab_force__"

_COMPREHENSIONS = (ast.ListComp, ast.SetComp, ast.DictComp)


def _targets(generators: list[ast.comprehension]) -> set[str]:
    return {node.id for generator in generators for node in ast.walk(generator.target) if isinstance(node, ast.Name)}


class _Loads(ast.NodeTransformer):
    def __init__(self, names: set[str], table: symtable.SymbolTable):
        self.names = names
        self.tables: list[symtable.SymbolTable | None] = [table]
        self.shadow: list[set[str]] = []
        self.used: set[int] = set()
        self.wrapped = 0
        self.unmatched = 0

    def _is_lazy_global(self, name: str) -> bool:
        table = self.tables[-1]
        if name not in self.names or table is None or any(name in names for names in self.shadow):
            return False
        try:
            return table.lookup(name).is_global()
        except KeyError:
            return False

    def _child(self, kind: str, name: str, lineno: int) -> symtable.SymbolTable | None:
        table = self.tables[-1]
        if table is None:
            return None
        for child in table.get_children():
            if (child.get_type(), child.get_name(), child.get_lineno()) == (kind, name, lineno):
                # `get_id`, not `id()`: each call of `get_children` makes
                # new wrappers, and a freed one's `id()` comes back.
                if child.get_id() not in self.used:
                    self.used.add(child.get_id())
                    return child
        self.unmatched += 1
        return None

    def _in(self, table: symtable.SymbolTable | None, nodes) -> None:
        self.tables.append(table)
        try:
            for node in nodes:
                self.visit(node)
        finally:
            self.tables.pop()

    def _visit_list(self, nodes) -> list:
        out = []
        for node in nodes:
            new = self.visit(node)
            if new is None:
                continue
            out.extend(new if isinstance(new, list) else [new])
        return out

    def visit_Name(self, node: ast.Name):
        if isinstance(node.ctx, ast.Load) and self._is_lazy_global(node.id):
            self.wrapped += 1
            call = ast.Call(func=ast.Name(FORCE, ast.Load()), args=[node], keywords=[])
            return ast.copy_location(call, node)
        return node

    def visit_Call(self, node: ast.Call):
        # A call resolves the proxy it calls, and rebinds it.
        if not isinstance(node.func, ast.Name):
            node.func = self.visit(node.func)
        node.args = [self.visit(arg) for arg in node.args]
        node.keywords = [self.visit(keyword) for keyword in node.keywords]
        return node

    def visit_Attribute(self, node: ast.Attribute):
        # So does a fetch off it.
        if not isinstance(node.value, ast.Name):
            node.value = self.visit(node.value)
        return node

    def _arguments(self, args: ast.arguments) -> None:
        args.defaults = [self.visit(value) for value in args.defaults]
        args.kw_defaults = [self.visit(value) if value is not None else None for value in args.kw_defaults]

    def _function(self, node: ast.FunctionDef | ast.AsyncFunctionDef):
        node.decorator_list = [self.visit(value) for value in node.decorator_list]
        self._arguments(node.args)
        if getattr(node, "type_params", None):
            return node
        child = self._child("function", node.name, node.lineno)
        self.tables.append(child)
        try:
            node.body = self._visit_list(node.body)
        finally:
            self.tables.pop()
        return node

    visit_FunctionDef = _function
    visit_AsyncFunctionDef = _function

    def visit_Lambda(self, node: ast.Lambda):
        self._arguments(node.args)
        child = self._child("function", "lambda", node.lineno)
        self.tables.append(child)
        try:
            node.body = self.visit(node.body)
        finally:
            self.tables.pop()
        return node

    def visit_ClassDef(self, node: ast.ClassDef):
        node.decorator_list = [self.visit(value) for value in node.decorator_list]
        node.bases = [self.visit(value) for value in node.bases]
        node.keywords = [self.visit(value) for value in node.keywords]
        if getattr(node, "type_params", None):
            return node
        child = self._child("class", node.name, node.lineno)
        self.tables.append(child)
        try:
            node.body = self._visit_list(node.body)
        finally:
            self.tables.pop()
        return node

    def _comprehension(self, node):
        self.shadow.append(_targets(node.generators))
        try:
            return self.generic_visit(node)
        finally:
            self.shadow.pop()

    visit_ListComp = _comprehension
    visit_SetComp = _comprehension
    visit_DictComp = _comprehension

    def visit_GeneratorExp(self, node: ast.GeneratorExp):
        # The first iterable runs in the enclosing scope, the rest in the
        # generator's own.
        first = node.generators[0]
        first.iter = self.visit(first.iter)
        child = self._child("function", "genexpr", node.lineno)
        self.tables.append(child)
        self.shadow.append(_targets(node.generators))
        try:
            first.ifs = [self.visit(value) for value in first.ifs]
            for generator in node.generators[1:]:
                self.visit(generator)
            node.elt = self.visit(node.elt)
        finally:
            self.shadow.pop()
            self.tables.pop()
        return node

    def visit_match_case(self, node: ast.match_case):
        # A pattern takes a name, never a call: `case Point():`.
        if node.guard is not None:
            node.guard = self.visit(node.guard)
        node.body = self._visit_list(node.body)
        return node

    def visit_AnnAssign(self, node: ast.AnnAssign):
        if node.value is not None:
            node.value = self.visit(node.value)
        return node

    def visit_arg(self, node: ast.arg):
        return node


def wrap_bare_loads(tree: ast.Module, source: str | bytes, filename: str, names: set[str]) -> tuple[int, int]:
    """
    Wrap every bare read of a global in `names`. Returns how many reads
    were wrapped and how many scopes could not be matched to a table.
    """
    if not names:
        return 0, 0
    loads = _Loads(names, symtable.symtable(source, filename, "exec"))
    tree.body = loads._visit_list(tree.body)
    return loads.wrapped, loads.unmatched
