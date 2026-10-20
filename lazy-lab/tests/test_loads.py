from __future__ import annotations

import ast
import textwrap

import pytest

from lazylab.loads import FORCE, wrap_bare_loads


def wrapped(source: str, names=("X",)) -> str:
    source = textwrap.dedent(source)
    tree = ast.parse(source)
    count, unmatched = wrap_bare_loads(tree, source, "<test>", set(names))
    assert unmatched == 0
    return ast.unparse(tree).replace(FORCE, "F")


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
        # A call and an attribute fetch resolve the proxy themselves.
        ("X()", "X()"),
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
        # Annotations and patterns are never rewritten.
        ("def f(a: X) -> X:\n    pass", "def f(a: X) -> X:\n    pass"),
        ("y: X = X", "y: X = F(X)"),
        ("match y:\n    case X():\n        pass", "match y:\n    case X():\n        pass"),
        # A name nobody made lazy.
        ("y = Z", "y = Z"),
    ],
)
def test_which_reads_are_wrapped(source, expected):
    assert wrapped(source) == expected


def test_with_flags_a_read_tests_the_flag_before_it_calls():
    tree = ast.parse("def f():\n    return ord(X)")
    wrap_bare_loads(tree, "def f():\n    return ord(X)", "<test>", {"X"}, flags=True)
    assert "ord(X if __lazylab_done_X__ else %s(X))" % FORCE in ast.unparse(tree)


def test_methods_of_two_classes_each_find_their_own_table():
    # Each `get_children` makes new wrappers, and a freed one's `id()`
    # comes back: matching on `id()` lost every method after the first
    # class.
    source = "\n".join("class C%d:\n    def m(self):\n        return X" % i for i in range(20))
    assert wrapped(source).count("F(X)") == 20
