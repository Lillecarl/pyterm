# lazy-lab

**Temporary.** A lab, not a source: it has no `flake.nix`, so the josh
export never copies it, and its checks stay out of `checks.all`. Delete
the directory and its lines in the root `default.nix` once it has
answered.

## The question

Can plain imports go lazy at import time, with no `lazy` keyword in the
source? A loader can rewrite a module's AST before it compiles, and a
policy can pick which imports to rewrite. This lab builds every way to
do that, holds them to one set of probes, and measures them on pymux.

## The answer

- **On 3.15, `ast-native`.** A loader sets `is_lazy` on the imports the
  policy picks, and 3.15 compiles its own lazy imports. It answers every
  probe as the interpreter's global mode does, passes pymux's suite
  under "everything-but" with eager's failures and no others, and costs
  the frame +0.0% everywhere. Completion: 4.05 M instructions to 1.49 M
  (-63%), 160 ms to 44 ms.
- **On 3.14, `ast-proxy-flags`.** Proxies, plus a rewrite of the reads
  3.15 resolves in C. It passes the same suite the same way on 3.14 and
  3.15, and costs the frame +0.8% on `measure` and +0.3% on `frame`.
  Completion: 4.35 M to 1.80 M (-59%), 183 ms to 60 ms.
- **Recursive works.** "everything-but" makes every import in pymux,
  its dependencies and the standard library lazy, except hypothesis and
  asyncssh, which register on import. That two-line deny list was all
  pymux's 3,446 tests asked for.
- **Not the shim's design.** The `lazy-imports` branch's proxies leak
  where a read is bare, and its `LazyModuleType` is the branch's +7–10%
  frame rise. Details below.

## The candidates

`lazylab/candidates/__init__.py` lists them.

| name | mechanism | runs on |
| --- | --- | --- |
| `eager` | nothing: the baseline | any |
| `ast-native` | the loader sets `is_lazy` on the AST, so 3.15 compiles its own lazy imports | 3.15 |
| `ast-proxy` | the loader rewrites each import to a proxy assignment, as the branch's shim | any |
| `ast-proxy-restore` | the same, and a module goes back to `ModuleType` once its last proxy resolves | any |
| `ast-proxy-loads` | the same, and a bare read of a lazy global resolves it; each module gets a class of its own | any |
| `ast-proxy-flags` | the same, with a flag per name that skips the resolving call once resolved | any |
| `native-filter` | `sys.set_lazy_imports("all")` with the policy as the filter: no rewrite | 3.15 |
| `lazy-modules` | the loader sets `__lazy_modules__` to a frozenset read off the bytecode: no rewrite | 3.15 |
| `lazy-modules-contains` | the same, set to an object whose `__contains__` asks the policy | 3.15 |
| `lazy-loader` | `importlib.util.LazyLoader` on each target module | any |
| `dunder-import` | `builtins.__import__` returns proxies | any |

Every candidate reads one policy, `lazylab/policy.py`: the signature
`sys.set_lazy_imports_filter` calls, `(importer, target, fromlist)`.
The presets: "ours" (every import our packages make), "foreign" (only
their imports of other projects), "everything", and "everything-but".
The rewrites pick the statements 3.15's global mode picks
(`lazylab/select.py`), so `ast-native` and `native-filter` differ by
mechanism alone.

## Recursive laziness

3.15's `lazy` keyword defers one statement: what the imported module
imports in turn stays eager. A loader rewrite cascades by construction,
because every module it loads is rewritten, so "everything" is the
recursive case. pymux's suite is its judge:
`checks.lazy-lab-pymux-unit-<version>` runs it eager and under each
candidate and policy, and groups what a run adds by the reason.

Under "everything" every lazy candidate, `ast-native` included, failed
the same ~50 tests: hypothesis checks at import that its strategies
registered, and asyncssh registers its key algorithms as each module
loads. Those are the two entries of "everything-but". The rest of what
the suite found were proxy bugs, each now fixed and held by a probe.

## What the probes say

`tests/test_parity.py` holds 27 probes, each in a fresh interpreter.
3.14 and 3.15 answer alike for every candidate both run.

- **A proxy leaks where a read is bare.** `ast-proxy`,
  `ast-proxy-restore` and `dunder-import` hand the proxy itself to
  `except` (a `TypeError`), to `format()` (its repr), to `is`, and to C
  code: `ord()` in wcwidth, `Mapping.register()` in `contextvars`,
  `dataclasses`' `ClassVar` test. `ast-proxy-loads` and
  `ast-proxy-flags` wrap those reads (`lazylab/loads.py`, scopes from
  `symtable`) and answer as 3.15 does.
- **`LazyModuleType` skips a module's own `__getattr__`** (PEP 562),
  because it reads through `object.__getattribute__`: `from ptyhost
  import Process` broke. A class per module with a property per lazy
  name does not.
- **A side effect of `import a.b` is an attribute.** pymux reads
  `anyio.to_thread` because some other module imported it. 3.15 keeps
  the submodule pending; `lazylab/submodules.py` does the same.
- **A package may lazily import its own submodule** and use it while it
  loads (`multiprocessing`), and **a name may be both a submodule and an
  object** (cryptography's `openssl.backend`). Both needed the proxy to
  tell itself from the module the import machinery set.
- **A callee may read its caller's frame**: anyio's lazy importer on
  3.15 does, from its module body. A proxy's `__call__` sits between
  them until the first call rebinds the name, so calls in module and
  class bodies are resolved first. A first call from inside a function
  still goes through the proxy; resolving every call cost the frame 6%.
- **`dunder-import` cannot see a `try`**, so `try: import x / except
  ImportError:` goes lazy and the fallback never runs; nor does it learn
  the name it binds.
- **`lazy-loader` defers only a plain `import m`**, not a module it
  cannot find, and cryptography refuses it outright ("substituted in
  sys.modules during a lazy load").
- **`importlib.import_module` stays eager everywhere** but under
  `lazy-loader`. A loader hook still makes that module's own imports
  lazy, however it was imported.

## What it costs

`checks.lazy-lab-measure-<version>` writes the tables. Instructions are
exact; the clock is one sandbox's. The frame rows are pymux's own
`measure_frame.py`, as mean and worst change against eager.

| | 3.14 | 3.15 |
| --- | --- | --- |
| completion, eager | 534 modules, 4.35 M | 512 modules, 4.05 M |
| `ast-native`, everything-but | | 164 modules, 1.49 M (-63%) |
| `native-filter`, everything-but | | 164 modules, 1.68 M (-58%) |
| `ast-proxy-flags`, everything-but | 162 modules, 1.80 M (-59%) | 166 modules, 1.72 M (-57%) |
| `lazy-modules-contains`, everything-but | | 160 modules, 1.53 M (-62%) |
| `lazy-modules`, everything-but | | 160 modules, 10.4 M (+158%) |
| frame `measure`, `ast-native` | | +0.0% |
| frame `measure`, `ast-proxy-flags` | +0.8% / +1.4% | +0.8% / +1.5% |
| frame `measure`, `ast-proxy-restore` foreign | +8.1% / +9.1% | +8.2% / +9.2% |

- **The branch's frame rise is `LazyModuleType`.** Run on the branch
  itself, split by code object (`measure/frame_breakdown.py`),
  `_LazyModuleType.__getattribute__` is the whole difference from main:
  all 182 extra instructions of `strip 4 panes (measure)` (2289 to
  2471, +8.0%) and all 3,016 of its `neighbours cold` (+6.5%). It is
  Python run on every fetch from outside a module with a name still
  lazy. `ast-proxy-restore` keeps that class and repeats the rise.
- **`native-filter` pays per import.** 3.15 calls the Python filter on
  every import everywhere: under "foreign" `import pymux.server` cost
  +68% instructions. `ast-native` applies the same policy once, at
  rewrite, and the rewrite cache keeps it.
- **`__lazy_modules__` is `ast-native` with no rewrite.** 3.15 tests
  `abs_name in __lazy_modules__` (`PySequence_Contains`) at each
  module-level import outside a `try`. It answers every probe as
  `ast-native`, and pymux's suite adds no failure under either policy.
  The check sees the absolute target only, never the fromlist, and a
  module that assigns its own `__lazy_modules__` replaces the loader's.
  `-contains` is a Python call per import: -62% on completion against
  `ast-native`'s -64% (1.53 M against 1.45 M), frame +0.0%. The
  frozenset variant loses: `dis` over every module's bytecode at each
  load is the whole +158%.
- **A rewrite pays on the first start.** With its cache empty,
  `ast-native` under everything-but takes completion from 113 ms eager
  to 330 ms (+193%), and `import pymux.server` under "ours" from 88 to
  71 ms against 53 ms warm. Every key the rewrite cache holds changes
  with the source path, so each new store path, and each sandbox with
  an empty `HOME`, starts cold. `lazy-modules-contains` reads the
  store's `.pyc` and is the same both times: 32 ms. tomllib assigns
  its own `__lazy_modules__`, the one stdlib module that does.
- **`ast-proxy-loads` against `-flags`**: the resolving call is about
  thirteen instructions a read, the flag test four: +1.8% against +0.8%
  on `measure`.

## Running it

    nix build --file . checks.lazy-lab-unit-314
    nix build --file . checks.lazy-lab-measure-315.run
    LAZYLAB_PYMUX_CANDIDATES=ast-native LAZYLAB_PYMUX_POLICIES=everything-but \
      nix build --file . checks.lazy-lab-pymux-unit-315.run

`python tests/matrix.py` prints every probe under every candidate the
interpreter runs, and `python -m lazylab CANDIDATE POLICY -m module`
runs any program with a candidate installed.

The 3.15 environment needed one bend: websockets 16.1 fails one of two
racy sync tests on 3.15 each run (`nix/python-bends.nix`).
