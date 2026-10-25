"""
What each mechanism does with each probe, held as a table.

Each row is 3.15's own answer, and the mechanisms that differ from it.
3.14 and 3.15 give the same answers for every mechanism both run, so a
row that changes is a change in a mechanism, and fails here.
"""

from __future__ import annotations

import pytest

from probes import MECHANISMS, PROBES, observe

# probe: (3.15's answer, {mechanism: its own answer})
EXPECTED: dict[str, tuple[object, dict[str, object]]] = {
    "defers": (False, {"eager": True}),
    "resolves-on-use": ([True, "module"], {}),
    # 3.15 binds a lazy `from m import x` at once when `m` is loaded.
    "already-loaded": ("type", {}),
    "bare-read-identity": (True, {}),
    "isinstance": ([True, True], {}),
    "except-clause": ("caught", {}),
    "match-class": ("a Thing", {}),
    "f-string": ("heavy!", {}),
    "concatenate": ("heavy!", {}),
    # An import made for its side effect is lost: deny it.
    "side-effect": ([], {"eager": ["one"]}),
    "fallback": ("fallback", {}),
    "missing": (
        [None, "ModuleNotFoundError", "ImportError"],
        {"eager": ["ModuleNotFoundError", "unreached", "unreached"]},
    ),
    # Laziness breaks the cycle that eager import cannot.
    "cycle": ("b sees a", {"eager": "ImportError"}),
    "submodules": (["inner", "other"], {}),
    "subclass": ([True, "Thing"], {}),
    "named-tuple-base": ([1, 2, "tuple"], {}),
    "star": (True, {}),
    "outside-fetch": (True, {}),
    "submodule-side-effect": ("inner", {}),
    "shadowed-submodule": (["the object", "the object"], {}),
    "caller-frame-at-import": ("app.calls_frames_at_import", {}),
    # The one call a proxy leaves between caller and callee: the first,
    # from inside a function.
    "caller-frame": ("app.calls_frames", {"proxies": "deferimport.proxy"}),
    "own-submodule": ("sub", {}),
    "module-getattr": ("late", {}),
    "import-module": (True, {}),
    "threads": (["Thing"] * 4, {}),
    "positions": (
        ["top_plain", "top_from", "in_if", "in_with", "in_for", "in_while", "in_match"],
        {"eager": []},
    ),
    "module-type": ("module", {"proxies": "DeferredModule"}),
    "retry-after-failure": (["RuntimeError", "second time"], {}),
    # PEP 810 keeps an import in `with` lazy, so it runs after the block.
    "inside-with": ("ModuleNotFoundError", {"eager": "found"}),
    # `get_type_hints` evaluates in the module's globals, which no rewrite
    # reaches: on 3.14 the hint is the proxy until the name resolves.
    "type-hints": (["type", True], {"proxies": ["LazyProxy", False]}),
    "own-class": (["module", "Thing"], {}),
}


def test_every_probe_has_a_row():
    assert set(EXPECTED) == set(PROBES)


@pytest.mark.parametrize("mechanism", MECHANISMS)
@pytest.mark.parametrize("probe", list(PROBES))
def test_probe(mechanism, probe, tmp_path_factory):
    common, own = EXPECTED[probe]
    cache = tmp_path_factory.getbasetemp() / "cache" / mechanism
    assert observe(mechanism, probe, cache=cache) == own.get(mechanism, common)
