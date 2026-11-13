from __future__ import annotations

import importlib
import sys
import types

from deferimport import submodules


class _Final(types.ModuleType):
    "A module type that takes no subclass, the way apsw's C `APSWModule` does."

    def __init_subclass__(cls, **kwargs):
        raise TypeError("type '_Final' is not an acceptable base type")


def test_a_package_whose_module_type_takes_no_subclass_imports_its_submodule_at_once(tmp_path, monkeypatch):
    package = tmp_path / "finalpkg"
    package.mkdir()
    (package / "__init__.py").write_text("")
    (package / "sub.py").write_text("VALUE = 42\n")
    monkeypatch.syspath_prepend(str(tmp_path))
    try:
        module = importlib.import_module("finalpkg")
        module.__class__ = _Final

        submodules.register("finalpkg", "sub")

        assert type(module) is _Final
        assert module.sub.VALUE == 42
        assert "sub" not in submodules.PENDING.get("finalpkg", set())
    finally:
        for name in ("finalpkg.sub", "finalpkg"):
            sys.modules.pop(name, None)


def test_a_submodule_still_loading_in_a_cycle_comes_from_sys_modules(tmp_path, monkeypatch):
    package = tmp_path / "cyclepkg"
    package.mkdir()
    (package / "__init__.py").write_text("")
    monkeypatch.syspath_prepend(str(tmp_path))
    try:
        module = importlib.import_module("cyclepkg")
        # What a cycle leaves: the submodule in sys.modules, not yet on its package.
        loading = types.ModuleType("cyclepkg.sub")
        sys.modules["cyclepkg.sub"] = loading
        submodules.PENDING["cyclepkg"].add("sub")

        assert submodules._getattr(module, "sub") is loading
    finally:
        submodules.PENDING.pop("cyclepkg", None)
        for name in ("cyclepkg.sub", "cyclepkg"):
            sys.modules.pop(name, None)
