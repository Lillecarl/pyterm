"""
Which module may import what, and the list the migration has to carry.

txterm is one layer: the front end for Textual. Everything under it
belongs to another package, and the point of Lillecarl/pymux#82 is that
this package can exist at all — a cell used to hold a prompt_toolkit
style string, so a cell held one renderer's spelling and a second front
end was impossible.

Two rules, and the second is the interesting one.

1. **No prompt_toolkit, anywhere.** `ptterm` is a prompt_toolkit widget
   and this package imports its parser, so the toolkit is in the build
   closure. Nothing here may reach for it.
2. **The imports from `ptterm` are written down.** That layer is pure
   and it belongs in `pyte`; it is in `ptterm` because that is where it
   was written. `PURE_LAYER` is what this package needs from it, which
   is what the move has to carry. A new name added here is a name added
   to the move. Lillecarl/pymux#11.
"""
import ast
from pathlib import Path

import pytest

import txterm

#: The package as it is installed, and not as it sits beside this file.
#: A check runs the tests against what it built.
PACKAGE = Path(txterm.__file__).parent

#: What this package takes from the pure layer of ptterm.
#:
#: **This is the migration manifest.** When the pure layer reaches
#: `pyte`, these are the modules to carry and the imports here to
#: rewrite. Nothing else of ptterm may appear.
PURE_LAYER = {
    "ptterm.colors",
    "ptterm.placeholders",
    "ptterm.screen",
    "ptterm.stream",
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
    The whole point of the split.

    `ptterm` is in the closure of this package, so the import would
    work. That is exactly why a test has to say no: it would work, and
    then a cell would carry two spellings again.
    """
    assert not {_root(module) for module in _imports(MODULES[name])} & NEVER


@pytest.mark.parametrize("name", sorted(MODULES))
def test_only_the_pure_layer_of_ptterm_is_used(name):
    """
    A module of ptterm that is not in `PURE_LAYER` is either a front end
    of prompt_toolkit, which this package must not touch, or a piece of
    the pure layer that nobody wrote down.
    """
    taken = {
        module
        for module in _imports(MODULES[name])
        if _root(module) == "ptterm"
    }
    assert taken <= PURE_LAYER, (
        "%s imports %s from ptterm; add it to PURE_LAYER, which is what "
        "the move to pyte has to carry" % (name, sorted(taken - PURE_LAYER))
    )


def test_the_manifest_is_what_the_package_really_needs():
    """
    And the other way round: a name in the list that nothing imports is
    a name the move would carry for nothing.

    This is also the guard on the reading. A reader that found no import
    anywhere would pass both tests above and say nothing at all.
    """
    taken = set()
    for path in MODULES.values():
        taken |= {
            module for module in _imports(path) if _root(module) == "ptterm"
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
