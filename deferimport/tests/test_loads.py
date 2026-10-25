from __future__ import annotations

import ast
import re
import textwrap

import pytest

from deferimport.loads import FORCE, wrap_reads
from deferimport.proxy import done


def wrapped(source: str, names=("X",)) -> str:
    source = textwrap.dedent(source)
    tree = ast.parse(source)
    _, unmatched = wrap_reads(tree, source, "<test>", set(names))
    assert unmatched == 0
    text = ast.unparse(tree).replace("X if %s else %s(X)" % (done("X"), FORCE), "F(X)")
    # `unparse` brackets the conditional where precedence asks for it.
    return re.sub(r"(?<![\w)])\(F\(X\)\)", "F(X)", text)


@pytest.mark.parametrize(
    ("source", "expected"),
    [
        # A bare read anywhere it means the global.
        ("y = X", "y = F(X)"),
        ("def f():\n    return X", "def f():\n    return F(X)"),
        ("def f():\n    return ord(X)", "def f():\n    return ord(F(X))"),
        ("try:\n    pass\nexcept X:\n    pass", "try:\n    pass\nexcept F(X):\n    pass"),
        ("def f():\n    return f'{X}'", "def f():\n    return f'{F(X)}'"),
        ("class C(X):\n    pass", "class C(F(X)):\n    pass"),
        ("f = lambda: X", "f = lambda: F(X)"),
        ("def f(a):\n    return [X for _ in a]", "def f(a):\n    return [F(X) for _ in a]"),
        ("def f(a):\n    return list((X for _ in a))", "def f(a):\n    return list((F(X) for _ in a))"),
        ("def f(a=X):\n    pass", "def f(a=F(X)):\n    pass"),
        ("@X\ndef f():\n    pass", "@F(X)\ndef f():\n    pass"),
        # A call in a body that runs once at import: through the proxy,
        # the callee's caller would be the proxy's `__call__`.
        ("X()", "F(X)()"),
        ("class C:\n    y = X()", "class C:\n    y = F(X)()"),
        # In a function the first call rebinds the name, and every later
        # one goes straight to the real function.
        ("def f():\n    return X()", "def f():\n    return X()"),
        # An attribute fetch resolves the proxy itself, and adds no frame.
        ("X.y", "X.y"),
        # A local, a parameter, a comprehension's own name: not the global.
        ("def f():\n    X = 1\n    return X", "def f():\n    X = 1\n    return X"),
        ("def f(X):\n    return X", "def f(X):\n    return X"),
        ("def f(a):\n    return [X for X in a]", "def f(a):\n    return [X for X in a]"),
        ("def f(a):\n    return list((X for X in a))", "def f(a):\n    return list((X for X in a))"),
        # A free variable of a closure is the enclosing function's.
        (
            "def f():\n    X = 1\n\n    def g():\n        return X\n    return g",
            "def f():\n    X = 1\n\n    def g():\n        return X\n    return g",
        ),
        # Annotations and patterns are never rewritten. A class a pattern
        # names is resolved before the match, because CPython takes only a
        # type there.
        ("def f(a: X) -> X:\n    pass", "def f(a: X) -> X:\n    pass"),
        ("y: X = X", "y: X = F(X)"),
        ("match y:\n    case X():\n        pass", "F(X)\nmatch y:\n    case X():\n        pass"),
        ("match y:\n    case X() | [X()]:\n        pass", "F(X)\nmatch y:\n    case X() | [X()]:\n        pass"),
        ("match y:\n    case Z():\n        pass", "match y:\n    case Z():\n        pass"),
        # A name nobody made lazy.
        ("y = Z", "y = Z"),
    ],
)
def test_which_reads_are_wrapped(source, expected):
    assert wrapped(source) == expected


def test_a_read_tests_the_flag_before_it_calls():
    tree = ast.parse("def f():\n    return ord(X)")
    wrap_reads(tree, "def f():\n    return ord(X)", "<test>", {"X"})
    assert "ord(X if %s else %s(X))" % (done("X"), FORCE) in ast.unparse(tree)


def test_methods_of_many_classes_each_find_their_own_table():
    # Each `get_children` makes new wrappers, and a freed one's `id()`
    # comes back: matching on `id()` lost every method after the first
    # class.
    source = "\n".join("class C%d:\n    def m(self):\n        return X" % i for i in range(20))
    assert wrapped(source).count("F(X)") == 20
