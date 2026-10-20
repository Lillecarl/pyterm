"""
What each candidate does with each probe, held as a table.

Each row is the answer most candidates give, and the candidates that
differ. The rows are `tests/matrix.py` output, read and judged: a row
that changes is a change in a mechanism, and fails here. 3.14 and 3.15
give the same answers for every candidate both run.
"""

from __future__ import annotations

import pytest

from lazylab import available
from probes import PROBES, observe

#: The proxies that leave a bare read alone. `ast-proxy-loads` resolves
#: one, as 3.15 does, and answers every probe as 3.15 does but the
#: module's class.
PROXIES = ("ast-proxy", "ast-proxy-restore", "dunder-import")

# probe: (common answer, {candidate: its own answer})
EXPECTED: dict[str, tuple[object, dict[str, object]]] = {
    "defers": (False, {"eager": True}),
    "resolves-on-use": ([True, "module"], {}),
    # 3.15 binds a lazy `from m import x` at once when `m` is loaded.
    "already-loaded": ("type", dict.fromkeys(PROXIES, "LazyProxy")),
    # A global read returns a proxy, which only an operation resolves.
    "bare-read-identity": (True, dict.fromkeys(PROXIES, False)),
    "isinstance": ([True, True], {}),
    # `except` wants a class and is given the proxy.
    "except-clause": ("caught", dict.fromkeys(PROXIES, "TypeError")),
    # `format()` takes `object.__format__`, which is `str()` of the proxy.
    "f-string": ("heavy!", dict.fromkeys(PROXIES, "the proxy's repr")),
    "concatenate": ("heavy!", {}),
    # Every lazy candidate loses an import made for its side effect.
    "side-effect": ([], {"eager": ["one"]}),
    # `__import__` cannot see the `try` around it.
    "fallback": ("fallback", {"dunder-import": "found"}),
    # A finder must find the module to defer it.
    "missing": (
        [None, "ModuleNotFoundError", "ImportError"],
        {name: ["ModuleNotFoundError", "unreached", "unreached"] for name in ("eager", "lazy-loader")},
    ),
    # Laziness breaks the cycle that eager import cannot.
    "cycle": ("b sees a", {"eager": "ImportError"}),
    "submodules": (["inner", "other"], {}),
    "subclass": ([True, "Thing"], {}),
    "named-tuple-base": ([1, 2, "tuple"], {}),
    "star": (True, {}),
    "outside-fetch": (True, {}),
    # Every proxy failed this before `lazylab/submodules.py`: pymux reads
    # `anyio.to_thread`, which another module's import put there.
    "submodule-side-effect": ("inner", {}),
    # Importing `shadow.thing` sets `shadow.thing` to the module; eagerly
    # the statement then sets the object. A proxy that knows its name
    # takes it back; `__import__` never learns the name it binds.
    "shadowed-submodule": (["the object", "the object"], {"dunder-import": ["the object", "module"]}),
    # Every proxy failed this as a cycle with itself, before `lazy_from`
    # learned to tell: multiprocessing's `from . import context`.
    "own-submodule": ("sub", {}),
    # `LazyModuleType` reads through `object.__getattribute__`, which
    # skips the module's own `__getattr__`. ptyhost has one.
    "module-getattr": ("late", dict.fromkeys(("ast-proxy", "ast-proxy-restore", "dunder-import"), "AttributeError")),
    # `import_module` hands back a module LazyLoader has not run.
    "import-module": (True, {"lazy-loader": False}),
    "threads": (["Thing"] * 4, {}),
    # LazyLoader defers only a plain import; `__import__` sees no `try`,
    # and `import a.b as c` fetches `b` off the proxy at once.
    "positions": (
        ["top_plain", "top_from", "in_if", "in_with", "in_for", "in_while", "in_match"],
        {
            "eager": [],
            "lazy-loader": ["top_plain"],
            "dunder-import": ["top_from", "in_if", "in_try", "in_with", "in_for", "in_while", "in_match"],
        },
    ),
    "module-type": (
        "module",
        {
            "ast-proxy": "LazyModuleType",
            "dunder-import": "LazyModuleType",
            "ast-proxy-loads": "LazyModule",
            "ast-proxy-flags": "LazyModule",
        },
    ),
}


def test_every_probe_has_a_row():
    assert set(EXPECTED) == set(PROBES)


@pytest.mark.parametrize("candidate", available())
@pytest.mark.parametrize("probe", list(PROBES))
def test_probe(candidate, probe, tmp_path_factory):
    common, own = EXPECTED[probe]
    cache = tmp_path_factory.getbasetemp() / "cache" / candidate
    assert observe(candidate, probe, cache=cache) == own.get(candidate, common)
