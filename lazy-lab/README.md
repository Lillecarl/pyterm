# lazy-lab

**Temporary.** A lab, not a source: it has no `flake.nix`, so the josh
export never copies it, and its checks stay out of `checks.all`. Delete
the directory and its lines in the root `default.nix` once it has
answered.

## The question

Can plain imports go lazy at import time, with no `lazy` keyword in the
source? A loader can rewrite a module's AST before it compiles, and a
policy can pick which imports to rewrite. This lab builds every way to
do that, holds them to one set of probes, and measures them.

## The candidates

`lazylab/candidates/__init__.py` lists them.

| name | mechanism | runs on |
| --- | --- | --- |
| `eager` | nothing: the baseline | any |
| `ast-native` | the loader sets `is_lazy` on the AST, so 3.15 compiles its own lazy imports | 3.15 |
| `ast-proxy` | the loader rewrites each import to a proxy assignment | any |
| `ast-proxy-restore` | the same, and a module goes back to `ModuleType` once its last proxy resolves | any |
| `ast-proxy-loads` | the same, and every bare read of a lazy global resolves it; each module gets a class of its own | any |
| `native-filter` | `sys.set_lazy_imports("all")` with the policy as the filter: no rewrite | 3.15 |
| `lazy-loader` | `importlib.util.LazyLoader` on each target module | any |
| `dunder-import` | `builtins.__import__` returns proxies | any |

Every candidate reads one policy, `lazylab/policy.py`: the signature
`sys.set_lazy_imports_filter` calls, `(importer, target, fromlist)`.
The rewrites pick the statements 3.15's global mode picks
(`lazylab/select.py`), so `ast-native` and `native-filter` differ by
mechanism alone, and the probes hold them equal.

## What the probes say

`tests/test_parity.py` holds 22 probes, each in a fresh interpreter.
3.14 and 3.15 answer alike for every candidate both run.

- **`ast-native` is 3.15's own lazy import.** It answers every probe as
  `native-filter` does, so a loader can choose native lazy imports per
  module and per import, with no `lazy` keyword in the source.
- **A proxy leaks wherever a read is bare.** `ast-proxy`,
  `ast-proxy-restore` and `dunder-import` hand the proxy itself to
  `except` (a `TypeError`), to `format()` (the proxy's repr), and to
  `is`. On pymux it reached `ord()` in wcwidth, and under "everything"
  `Mapping.register()` in `contextvars`. The branch's shim has the same
  leak.
- **`ast-proxy-loads` closes it on 3.14.** The rewrite already has the
  AST, so it wraps each bare read of a lazy global
  (`lazylab/loads.py`, scopes from `symtable`). It answers every probe
  as 3.15 does.
- **`dunder-import` cannot see a `try`**, so `try: import x / except
  ImportError:` goes lazy and the fallback never runs.
- **`lazy-loader` defers only a plain `import m`**, and not a module
  it cannot find. `from m import x` loads `m` at once.
- **Every lazy candidate loses an import made for its side effect**, as
  3.15 does. pymux registers its commands with an explicit
  `import_module` and `register`, so it loses none: the completion
  parser has 142 commands under every candidate.
- **`importlib.import_module` stays eager everywhere** but under
  `lazy-loader`: it returns the module, and the caller uses it at once.
  A loader hook still makes that module's own imports lazy, however it
  was imported.

## Running it

    nix build --file . checks.lazy-lab-unit-314
    nix build --file . checks.lazy-lab-unit-315

`python tests/matrix.py` prints every probe under every candidate the
interpreter runs, and `python -m lazylab CANDIDATE POLICY -m module`
runs any program with a candidate installed.
