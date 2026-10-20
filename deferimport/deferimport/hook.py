"""
The finder and the loader that rewrite a module before it compiles.

The loader overrides `get_code`, not `source_to_code`. A
`SourceFileLoader` calls `source_to_code` only when its bytecode cache
misses, and an installed package carries a `__pycache__` beside every
source -- read-only in the nix store -- so a `source_to_code` override
never runs. The rewritten bytecode goes to a cache of its own instead,
keyed by the mechanism and the policy: parsing and compiling every
module at each start would cost more than the laziness saves.
"""

from __future__ import annotations

import ast
import hashlib
import importlib.machinery
import marshal
import os
import symtable  # noqa: F401  (loaded before the hook: see `_NEVER`)
import sys
import tokenize  # noqa: F401  (loaded before the hook: see `_NEVER`)
from pathlib import Path
from typing import TYPE_CHECKING, Protocol, override

from . import select

if TYPE_CHECKING:
    import types

    from .policy import Policy

__all__ = ["STATS", "Finder", "Transform", "cache_directory", "install"]

#: Modules the hook loaded, statements it made lazy, and cache hits.
STATS = {"modules": 0, "lazy": 0, "cached": 0}

#: Never rewritten: this package, and what it needs to rewrite. Each is
#: imported above, so it is loaded before the hook installs: on 3.15
#: `tokenize` is not loaded at start, and decoding a source rewrote it
#: re-entrantly.
_NEVER = ("deferimport", "ast", "importlib", "encodings", "marshal", "hashlib", "tokenize", "symtable")

#: Moves with every change to what a rewrite emits, so a cache written by
#: an older one is never read.
_VERSION = b"deferimport-1"


def cache_directory() -> Path:
    "`DEFERIMPORT_CACHE`, or a directory of the user's cache."
    configured = os.environ.get("DEFERIMPORT_CACHE")
    if configured:
        return Path(configured)
    base = os.environ.get("XDG_CACHE_HOME") or os.path.join(os.path.expanduser("~"), ".cache")
    return Path(base) / "deferimport"


class Transform(Protocol):
    name: str

    def rewrite(
        self, tree: ast.Module, importer: str, package: str | None, policy: Policy, filename: str, source: bytes
    ) -> int:
        "Change `tree` in place and return how many statements went lazy."

    def prepare(self, module: types.ModuleType, lazy: int) -> None:
        "Run before the module's code, with `lazy` its count from `rewrite`."

    def finish(self, module: types.ModuleType, lazy: int) -> None:
        "Run after the module's code."


class _Loader(importlib.machinery.SourceFileLoader):
    def __init__(self, fullname: str, path: str, finder: Finder):
        super().__init__(fullname, path)
        self._finder = finder
        self._lazy = 0

    def _cache_path(self, fullname: str) -> Path:
        name = "%s.%s.%s.pyc" % (fullname, sys.implementation.cache_tag, self._finder.fingerprint)
        return self._finder.cache / name

    @override
    def get_code(self, fullname):
        source_path = self.get_filename(fullname)
        stats = self.path_stats(source_path)
        # The source's own path is in the key too: two installs of one
        # module share a name and nothing else.
        header = b"%d:%d:%s\n" % (int(stats["mtime"] * 1e9), stats.get("size", 0), os.fsencode(source_path))
        cached = self._cache_path(fullname)
        STATS["modules"] += 1
        try:
            data = cached.read_bytes()
        except OSError:
            data = b""
        if data.startswith(header):
            lazy, code = marshal.loads(data[len(header) :])
            STATS["lazy"] += lazy
            STATS["cached"] += 1
            self._lazy = lazy
            return code
        source = self.get_data(source_path)
        tree = select.split_imports(ast.parse(source, source_path))
        package = fullname if self.is_package(fullname) else fullname.rpartition(".")[0]
        lazy = self._finder.transform.rewrite(tree, fullname, package or None, self._finder.policy, source_path, source)
        code = compile(ast.fix_missing_locations(tree), source_path, "exec", dont_inherit=True)
        STATS["lazy"] += lazy
        self._lazy = lazy
        # A cache that cannot be written costs the next start a parse,
        # and nothing else.
        try:
            cached.parent.mkdir(parents=True, exist_ok=True)
            partial = cached.with_suffix(".%d.tmp" % os.getpid())
            partial.write_bytes(header + marshal.dumps((lazy, code)))
            partial.replace(cached)
        except OSError:
            pass
        return code

    @override
    def exec_module(self, module):
        code = self.get_code(module.__name__)
        self._finder.transform.prepare(module, self._lazy)
        exec(code, module.__dict__)
        self._finder.transform.finish(module, self._lazy)


class Finder:
    "Hands every source module the policy covers to a rewriting loader."

    _deferimport = True

    def __init__(self, transform: Transform, policy: Policy, cache: Path):
        self.transform = transform
        self.policy = policy
        self.cache = cache
        self.fingerprint = hashlib.sha256(
            b"\0".join((_VERSION, transform.name.encode(), policy.spec().encode()))
        ).hexdigest()[:16]

    def find_spec(self, fullname, path, target=None):
        if fullname.partition(".")[0] in _NEVER or not self.policy.covers_importer(fullname):
            return None
        # A test module is pytest's to rewrite, for its asserts.
        last = fullname.rpartition(".")[2]
        if last == "conftest" or last.startswith("test_"):
            return None
        spec = importlib.machinery.PathFinder.find_spec(fullname, path, target)
        if spec is None or type(spec.loader) is not importlib.machinery.SourceFileLoader:
            return spec
        spec.loader = _Loader(fullname, spec.origin, self)
        return spec

    def invalidate_caches(self):
        importlib.machinery.PathFinder.invalidate_caches()


def install(transform: Transform, policy: Policy, cache: Path) -> Finder:
    finder = Finder(transform, policy, cache)
    sys.meta_path.insert(0, finder)
    return finder
