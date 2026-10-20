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
| `native-filter` | `sys.set_lazy_imports("all")` with the policy as the filter: no rewrite | 3.15 |
| `lazy-loader` | `importlib.util.LazyLoader` on each target module | any |
| `dunder-import` | `builtins.__import__` returns proxies | any |

Every candidate reads one policy, `lazylab/policy.py`: the signature
`sys.set_lazy_imports_filter` calls, `(importer, target, fromlist)`.
The rewrites pick the statements 3.15's global mode picks
(`lazylab/select.py`), so `ast-native` and `native-filter` differ by
mechanism alone, and the probes hold them equal.

## Running it

    nix build --file . checks.lazy-lab-unit-314
    nix build --file . checks.lazy-lab-unit-315

`python tests/matrix.py` prints every probe under every candidate the
interpreter runs, and `python -m lazylab CANDIDATE POLICY -m module`
runs any program with a candidate installed.
