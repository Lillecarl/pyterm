"""
The questions each mechanism answers, each in a fresh interpreter.

A probe is code that leaves its answer in `result`. `observe` runs it
under one mechanism -- `eager`, `native` or `proxies` -- with
`tests/fixtures` on the path, and returns the answer as JSON gave it
back. Most were found by pymux's suite with every import lazy, and each
holds the fix it found.

The policy names the dependencies as targets, never the modules a probe
loads, and a probe loads through `load`, which is
`importlib.import_module`: otherwise the probe's own import goes lazy,
and a row measures the probe instead of the fixture.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import textwrap
from pathlib import Path

__all__ = ["FIXTURES", "MECHANISMS", "POLICY", "PROBES", "observe", "run"]

FIXTURES = Path(__file__).parent / "fixtures"
PACKAGE = Path(__file__).parent.parent

#: What this interpreter runs: 3.15 has lazy imports of its own.
MECHANISMS = ["eager", *(["native"] if sys.version_info >= (3, 15) else []), "proxies"]

POLICY = "targets=heavy,plugins,missing_mod,cycle_b,pkg_two,marks,typing,selfpkg,shadow,frames,flaky,hidden_mod"

_PREAMBLE = """
import importlib, os, sys
load = importlib.import_module
ran = lambda: os.environ.get("DEFERIMPORT_TEST_HEAVY_RAN") == "1"
"""

PROBES: dict[str, str] = {
    # Loading the module leaves its import undone.
    "defers": """
load("app.plain")
result = ran()
""",
    # The first use imports, and the global holds the real thing after.
    "resolves-on-use": """
m = load("app.plain")
m.use()
result = [ran(), type(vars(m)["heavy"]).__name__]
""",
    # The dependency is loaded already when the lazy statement runs.
    "already-loaded": """
load("heavy")
m = load("app.members")
result = type(vars(m)["Thing"]).__name__
""",
    # A bare read of the global, before anything else touched it.
    "bare-read-identity": """
m = load("app.members")
seen = m.raw()
result = seen is load("heavy").Thing
""",
    "isinstance": """
m = load("app.members")
heavy = load("heavy")
result = [m.is_thing(heavy.Thing()), m.is_subclass(heavy.Thing)]
""",
    # `except Boom:` with Boom still lazy.
    "except-clause": """
try:
    result = load("app.members").catch()
except Exception as e:
    result = type(e).__name__
""",
    # `case Thing():` with Thing still lazy: CPython takes only a type
    # there. The MCP SDK's server loop matches this way.
    "match-class": """
result = load("app.members").matched(load("heavy").Thing())
""",
    # A string constant formatted before anything resolved it.
    "f-string": """
result = load("app.members").formatted()
if result.startswith("<lazy "):
    result = "the proxy's repr"
""",
    "concatenate": """
result = load("app.members").concatenated()
""",
    # An import wanted for what it does, not for a name.
    "side-effect": """
result = load("app.registers").registered()
""",
    # `try: import x / except ImportError:` stays eager.
    "fallback": """
result = load("app.fallback").which()
""",
    # Where a missing module or member says so: at import, or at use.
    "missing": """
try:
    m = load("app.missing")
    imported = None
except Exception as e:
    imported = type(e).__name__
module = member = "unreached"
if imported is None:
    try:
        m.use_module()
    except Exception as e:
        module = type(e).__name__
    try:
        m.use_member()
    except Exception as e:
        member = type(e).__name__
result = [imported, module, member]
""",
    # A cycle that fails eagerly, and need not lazily.
    "cycle": """
try:
    result = load("cycle_a").get()
except Exception as e:
    result = type(e).__name__
""",
    # `import a.b` then `import a.c`: both bind `a`, and both must work.
    "submodules": """
try:
    result = list(load("app.submodules").both())
except Exception as e:
    result = type(e).__name__
""",
    # A base class at module level forces the import at once.
    "subclass": """
m = load("app.subclass")
result = [ran(), m.Mine.__mro__[1].__name__]
""",
    # A base that is a function with `__mro_entries__`, not a class.
    "named-tuple-base": """
point = load("app.named_tuple").Point(1, 2)
result = [point.x, point.y, type(point).__mro__[1].__name__]
""",
    # `from m import *` of a module whose names are still lazy.
    "star": """
m = load("app.star_user")
result = m.thing() is load("heavy").Thing
""",
    # Another module fetching a lazy name off this one.
    "outside-fetch": """
m = load("app.members")
result = m.Thing is load("heavy").Thing
""",
    # `a.b` read off `a`, where only another module's lazy `import a.b`
    # would have put it.
    "submodule-side-effect": """
try:
    result = load("app.reads_inner").read()
except Exception as e:
    result = type(e).__name__
""",
    # `from pkg.thing import thing` in pkg: importing the submodule sets
    # `pkg.thing` to the module, and the statement sets it back.
    "shadowed-submodule": """
m = load("shadow")
first, second = m.thing, m.thing
result = [first, second if isinstance(second, str) else type(second).__name__]
""",
    # A lazily imported callee that reads `sys._getframe(1)`, called first
    # from a module body, and first from inside a function.
    "caller-frame-at-import": """
result = load("app.calls_frames_at_import").CALLER
""",
    "caller-frame": """
result = load("app.calls_frames").who()
""",
    # A package's `from . import sub`, used while the package loads.
    "own-submodule": """
try:
    result = load("selfpkg").VALUE
except Exception as e:
    result = type(e).__name__
""",
    # A module's own `__getattr__` (PEP 562), while a lazy name in it is
    # still pending.
    "module-getattr": """
try:
    result = load("app.dynamic").LATE
except Exception as e:
    result = type(e).__name__
""",
    # `importlib.import_module` at module level, as a dependency does it.
    "import-module": """
load("app.by_function")
result = ran()
""",
    # Four threads at the first use, while the import sleeps.
    "threads": """
import os, threading
os.environ["DEFERIMPORT_TEST_SLOW_HEAVY"] = "1"
m = load("app.plain")
out = []
def worker():
    try:
        out.append(type(m.use()).__name__)
    except Exception as e:
        out.append(type(e).__name__)
threads = [threading.Thread(target=worker) for _ in range(4)]
for t in threads: t.start()
for t in threads: t.join()
result = sorted(out)
""",
    # Which positions went lazy.
    "positions": """
p = load("app.positions")
names = ["top_plain", "top_from", "in_if", "in_try", "in_with", "in_for", "in_while", "in_match"]
lazy = lambda value: type(value).__name__ in ("lazy_import", "LazyProxy", "_LazyModule")
found = [name for name in names if lazy(vars(p)[name])]
if lazy(vars(p.Holder)["in_class"]):
    found.append("in_class")
result = found
""",
    # The module's class once everything in it resolved.
    "module-type": """
m = load("app.plain")
m.use()
result = type(m).__name__
""",
    # An import that fails, then is used again: 3.15 keeps the lazy name
    # and tries again; a proxy must not keep the failure.
    "retry-after-failure": """
answers = []
for _ in range(2):
    try:
        m = load("app.uses_flaky")
        answers.append(m.use())
    except Exception as e:
        answers.append(type(e).__name__)
result = answers
""",
    # An import that works only inside the `with` around it. A lazy one
    # runs after the block, outside it: a difference from eager, on 3.15
    # as well (PEP 810 keeps `with` lazy).
    "inside-with": """
try:
    result = load("app.with_path").use()
except Exception as e:
    result = type(e).__name__
""",
    # `typing.get_type_hints` evaluates a string annotation in the
    # module's globals, where the name is still lazy.
    "type-hints": """
import typing
hint = typing.get_type_hints(load("app.hints").take)["value"]
result = [type(hint).__name__, hint is load("heavy").Thing]
""",
    # A module that sets its own class while it loads, after the
    # mechanism set one.
    "own-class": """
m = load("app.selfclass")
result = [type(m.heavy).__name__, type(m.use()).__name__]
""",
}


def observe(mechanism: str, probe: str, *, cache: Path, policy: str = POLICY) -> object:
    return run(mechanism, PROBES[probe], policy=policy, cache=cache)


def run(
    mechanism: str,
    code: str,
    *,
    policy: str = POLICY,
    cache: Path | None = None,
    fixtures: Path = FIXTURES,
    env: dict[str, str] | None = None,
) -> object:
    "Run `code` under `mechanism` and return its `result`."
    install = (
        ""
        if mechanism == "eager"
        else "import deferimport\ndeferimport.install(%r, mechanism=%r)\n" % (policy, mechanism)
    )
    code = install + _PREAMBLE + textwrap.dedent(code) + "\nimport json\nprint('\\nRESULT ' + json.dumps(result))\n"
    environment = dict(os.environ)
    environment["PYTHONPATH"] = os.pathsep.join([str(fixtures), str(PACKAGE)])
    environment["PYTHONDONTWRITEBYTECODE"] = "1"
    environment.pop("DEFERIMPORT", None)
    if cache is not None:
        environment["DEFERIMPORT_CACHE"] = str(cache)
    environment |= env or {}
    done = subprocess.run(
        [sys.executable, "-c", code],
        env=environment,
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )
    for line in reversed(done.stdout.splitlines()):
        if line.startswith("RESULT "):
            return json.loads(line.removeprefix("RESULT "))
    raise AssertionError(
        "%s gave no result (exit %d):\n%s\n%s%s" % (mechanism, done.returncode, code, done.stdout, done.stderr)
    )
