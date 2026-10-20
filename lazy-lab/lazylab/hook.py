"""
The finder and loader every AST rewrite installs.

The loader overrides `get_code`, not `source_to_code`. A
`SourceFileLoader` calls `source_to_code` only when its bytecode cache
misses, and the nix store holds a `__pycache__` beside every source, so
a `source_to_code` override never runs for an installed package and the
lab would compare eager to eager. The rewritten bytecode goes to a cache
of its own, `LAZYLAB_CACHE`, keyed by the transform and the policy.

`STATS` counts what the hook did, so a measurement that rewrote nothing
says so instead of reading as "no difference".
"""

from __future__ import annotations

import ast
import hashlib
import importlib.machinery
import importlib.util
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

__all__ = ["STATS", "RewriteFinder", "Transform", "install"]

#: Modules the hook loaded, statements it made lazy, and cache hits.
STATS = {"modules": 0, "lazy": 0, "cached": 0}

#: Never rewritten: the lab itself, and what it needs to rewrite. Each is
#: imported above, so it is loaded before the hook installs: on 3.15
#: `tokenize` was not, and decoding a source rewrote it re-entrantly.
_NEVER = ("lazylab", "ast", "importlib", "encodings", "marshal", "hashlib", "tokenize", "symtable")

_VERSION = b"lazylab-1"


class Transform(Protocol):
    name: str

    def rewrite(
        self, tree: ast.Module, importer: str, package: str | None, policy: Policy, filename: str, source: bytes
    ) -> int:
        "Change `tree` in place and return how many statements went lazy."

    def prepare(self, module: types.ModuleType, lazy: int) -> None:
        "Run before the module's code, with `lazy` its count from `rewrite`."


class _RewriteLoader(importlib.machinery.SourceFileLoader):
    def __init__(self, fullname: str, path: str, finder: RewriteFinder):
        super().__init__(fullname, path)
        self._finder = finder
        self._lazy = 0

    def _cache_path(self, fullname: str) -> Path | None:
        root = os.environ.get("LAZYLAB_CACHE")
        if not root:
            return None
        return Path(root) / ("%s.%s.%s.pyc" % (fullname, sys.implementation.cache_tag, self._finder.fingerprint))

    @override
    def get_code(self, fullname):
        source_path = self.get_filename(fullname)
        stats = self.path_stats(source_path)
        header = b"%d:%d\n" % (int(stats["mtime"] * 1e9), stats.get("size", 0))
        cached = self._cache_path(fullname)
        STATS["modules"] += 1
        if cached is not None and cached.exists():
            data = cached.read_bytes()
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
        if cached is not None:
            cached.parent.mkdir(parents=True, exist_ok=True)
            partial = cached.with_suffix(".%d.tmp" % os.getpid())
            partial.write_bytes(header + marshal.dumps((lazy, code)))
            partial.replace(cached)
        return code

    @override
    def exec_module(self, module):
        code = self.get_code(module.__name__)
        self._finder.transform.prepare(module, self._lazy)
        exec(code, module.__dict__)


class RewriteFinder:
    "Hands every source module the policy covers to a rewriting loader."

    _lazylab = True

    def __init__(self, transform: Transform, policy: Policy):
        self.transform = transform
        self.policy = policy
        self.fingerprint = hashlib.sha256(
            b"\0".join((_VERSION, transform.name.encode(), policy.spec().encode()))
        ).hexdigest()[:16]

    def find_spec(self, fullname, path, target=None):
        if fullname.partition(".")[0] in _NEVER or not self.policy.covers_importer(fullname):
            return None
        # A test module is pytest's to rewrite, for its asserts. The suite
        # judges the rewrite here, and is not what is rewritten.
        last = fullname.rpartition(".")[2]
        if last == "conftest" or last.startswith("test_"):
            return None
        spec = importlib.machinery.PathFinder.find_spec(fullname, path, target)
        if spec is None or type(spec.loader) is not importlib.machinery.SourceFileLoader:
            return spec
        spec.loader = _RewriteLoader(fullname, spec.origin, self)
        return spec

    def invalidate_caches(self):
        importlib.machinery.PathFinder.invalidate_caches()


def install(transform: Transform, policy: Policy) -> RewriteFinder:
    finder = RewriteFinder(transform, policy)
    sys.meta_path.insert(0, finder)
    return finder
