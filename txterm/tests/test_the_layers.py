"""
Which module may import what.

txterm is one layer: the front end for Textual. Everything under it
belongs to another package, and the point of Lillecarl/pymux#82 is that
this package can exist at all — a cell used to hold a prompt_toolkit
style string, so a cell held one renderer's spelling and a second front
end was impossible.

Two rules.

1. **No prompt_toolkit, anywhere.** It is not in the closure any more
   either: the pure layer moved out of `ptterm` and into `pyte`, so the
   toolkit is no longer a build dependency of this package. The rule
   stays, because the closure is not what a rule is for.
2. **The imports from `pyte` are written down.** A front end draws cells
   and sends keys, so what it needs is the screen, the parser that feeds
   it, and the two tables that say what a cell holds. `ptterm` takes
   almost the same five, and its own copy of this file says so.
"""
import ast
from pathlib import Path

import pytest

import txterm

#: The package as it is installed, and not as it sits beside this file.
#: A check runs the tests against what it built.
PACKAGE = Path(txterm.__file__).parent

#: What this package takes from the pure layer.
#:
#: Nothing else of `pyte` may appear. A name added here says the front
#: end grew, and that is worth reading in a diff.
PURE_LAYER = {
    "pyte.colors",
    "pyte.images",
    "pyte.placeholders",
    "pyte.screen",
    "pyte.streams",
}

#: The toolkit this package draws with, and the one it may never touch.
DRAWS_WITH = {"textual", "rich"}
NEVER = {"prompt_toolkit"}


def _modules():
    "Every module of the package, by name."
    found = {}
    for path in sorted(PACKAGE.rglob("*.py")):
        if "__pycache__" in path.parts:
            continue
        relative = path.relative_to(PACKAGE).with_suffix("")
        parts = list(relative.parts)
        if parts[-1] == "__init__":
            parts.pop()
        found[".".join(parts) or "__init__"] = path
    return found


MODULES = _modules()


def _imports(path: Path):
    """
    The outside modules that one file imports, by their full name.

    A relative import names something inside this package, and the rules
    here are about what comes from outside it.
    """
    outside = set()
    for node in ast.walk(ast.parse(path.read_text())):
        if isinstance(node, ast.Import):
            for alias in node.names:
                outside.add(alias.name)
        elif isinstance(node, ast.ImportFrom) and not node.level:
            outside.add(node.module or "")
    return outside


def _root(name: str) -> str:
    return name.split(".")[0]


@pytest.mark.parametrize("name", sorted(MODULES))
def test_nothing_imports_prompt_toolkit(name):
    """
    The whole point of the split. `ptterm` is not in the closure of this
    package any more, so the import would not even resolve; the rule
    stays because a rule is not the closure.
    """
    assert not {_root(module) for module in _imports(MODULES[name])} & NEVER


@pytest.mark.parametrize("name", sorted(MODULES))
def test_only_the_pure_layer_of_pyte_is_used(name):
    """
    A module of `pyte` that is not in `PURE_LAYER` is either something
    upstream left behind, or a piece of the screen that nobody wrote
    down here.
    """
    taken = {
        module for module in _imports(MODULES[name]) if _root(module) == "pyte"
    }
    assert taken <= PURE_LAYER, (
        "%s imports %s from pyte; add it to PURE_LAYER"
        % (name, sorted(taken - PURE_LAYER))
    )


def test_the_list_is_what_the_package_really_needs():
    """
    And the other way round: a name in the list that nothing imports is
    a name that says the front end is bigger than it is.

    This is also the guard on the reading. A reader that found no import
    anywhere would pass both tests above and say nothing at all.
    """
    taken = set()
    for path in MODULES.values():
        taken |= {
            module for module in _imports(path) if _root(module) == "pyte"
        }
    assert taken == PURE_LAYER


def test_the_widget_draws_with_textual():
    "The guard on the reading, from the other side."
    outside = {_root(module) for module in _imports(MODULES["terminal"])}
    assert DRAWS_WITH <= outside


def test_the_pty_comes_from_ptyhost():
    """
    Only the widget runs a program. `ptyhost` is the package that does
    it, and nothing here parses what it hands back. Lillecarl/pymux#85.
    """
    reaching = sorted(
        name
        for name in MODULES
        if any(_root(module) == "ptyhost" for module in _imports(MODULES[name]))
    )
    assert reaching == ["app", "terminal"]
