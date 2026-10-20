# deferimport

> This repository is a copy. Work on deferimport happens in
> [pyterm](https://github.com/Lillecarl/pyterm), which exports its `deferimport/`
> directory here on every push. Send changes there, and issues to
> [Lillecarl/pymux](https://github.com/Lillecarl/pymux/issues).
> The docs are at <https://lillecarl.github.io/deferimport/>.

<!-- The lines above are pyterm's nix/shared/readme-head.md, written by sync-sources. -->

Make plain imports lazy at import time, with no `lazy` keyword in the
source.

    import deferimport
    deferimport.install("deny=hypothesis,asyncssh")

`install` puts a finder first on `sys.meta_path`, and in every module
loaded after it each module-scope import the policy picks goes lazy, in
the positions 3.15 picks itself. The laziness
cascades through every dependency and the standard library, where the
`lazy` keyword makes one statement lazy and leaves what that module
imports eager.

## The two mechanisms

- **3.15** has lazy imports of its own (PEP 810). The loader sets
  `__lazy_modules__` to an object that asks the policy at each import,
  and rewrites nothing: a module compiles from the bytecode its
  installer wrote. The policy sees the target, never the fromlist.
- **3.14** has none, so each module is rewritten before it compiles,
  and each import becomes a proxy that rebinds its
  name on first use, and the reads a proxy would leak are rewritten to
  resolve it first. A module that holds one gets a class of its own,
  with a property per name still lazy.

Both pass pymux's whole suite with every import lazy but two packages
that register on import, and they answer every probe in
`tests/test_parity.py` as 3.15 does, but:

- **A first call from inside a function**, on 3.14, to a callee that
  reads its caller's frame sees the proxy as that caller. The first
  call rebinds the name; resolving every call cost a frame of pymux 6%.
- **`typing.get_type_hints`**, on 3.14, evaluates a string annotation in
  the module's globals, where an unresolved name is still the proxy.

## What not to make lazy

Deny an import made for what it does, a module that registers itself
on import, and a module that replaces itself in `sys.modules`. A lazy
import inside a `with` runs after the block, on 3.15 as well.

## Measured

pyterm's `lazy-lab/` holds the candidates this was chosen from, and
their numbers on pymux. With every import lazy but hypothesis and
asyncssh, the parser behind a shell's Tab costs 62% fewer instructions
on 3.15 and 59% fewer on 3.14, and a frame of pymux +0.0% and +0.3%.

A rewrite on 3.15, setting `is_lazy`, measured two points cheaper with
its cache warm, and three times eager's start with it cold: 330 ms
against 113. Every new install path starts cold, so 3.15 rewrites
nothing.

## Other ways, and why not them

| | what goes lazy | source changes | where it falls short here |
| --- | --- | --- | --- |
| PEP 810 `lazy` keyword (3.15) | one statement | every import, by hand | does not cascade into what the module imports |
| `sys.set_lazy_imports("all")` + filter (3.15) | every module-scope import | none | the filter is a Python call at every import of every module: up to +68% instructions |
| Cinder, PEP 690 (rejected 2022) | every module-scope import | none | an interpreter fork |
| `importlib.util.LazyLoader`, Mercurial's demandimport | a whole module, on attribute fetch | none | `from m import x` loads `m` at once; cryptography refuses it |
| `lazy_loader` (SPEC 1), apipkg, transformers' `_LazyModule` | a package's attributes, through PEP 562 | each package's `__init__` | only packages written for it |
| `lazy-object-proxy` and the like | one object | each use | `except`, `type()` and `is` see the proxy |

PEP 690 was rejected for a global switch every project would have to
test both ways. A policy per importer, and `DEFERIMPORT=eager`, are this
package's answer to that.

`DEFERIMPORT=eager` makes `install` do nothing, so one suite runs both
ways. `-p deferimport.pytest_plugin` runs a suite under
`DEFERIMPORT_POLICY`. On 3.14, rewritten bytecode is cached in
`DEFERIMPORT_CACHE`, by default the user's cache directory.

<!-- The lines below are pyterm's nix/shared/readme-tail.md, written by sync-sources. -->

## Building

    nix build github:Lillecarl/deferimport    # from this repository alone
    nix build --file . deferimport            # in a checkout of pyterm

The suites that judge it run in pyterm, as `checks.deferimport-*`.

## The collection

deferimport is one source of [pyterm](https://github.com/Lillecarl/pyterm), and
each source claims one job:

| source | job |
| --- | --- |
| [pyte](https://lillecarl.github.io/pyte/) | parse, and hold a screen |
| [ptyhost](https://lillecarl.github.io/ptyhost/) | run a program on a pty, and carry its bytes |
| [ptterm](https://lillecarl.github.io/ptterm/) | draw one terminal, with prompt-toolkit |
| [txterm](https://lillecarl.github.io/txterm/) | draw one terminal, with Textual |
| [pymux](https://lillecarl.github.io/pymux/) | arrange several of them |
| [pysmithay](https://lillecarl.github.io/pysmithay/) | a headless Wayland compositor, for a GUI program in a pane |
| [pyterm-pytest](https://lillecarl.github.io/pyterm-pytest/) | the test equipment the suites share |
| [deferimport](https://lillecarl.github.io/deferimport/) | make imports lazy, without a keyword |

[pyterm's site](https://lillecarl.github.io/pyterm/) holds every source's
docs.
