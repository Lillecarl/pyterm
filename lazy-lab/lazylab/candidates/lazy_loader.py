"""
`importlib.util.LazyLoader`, the standard library's answer.

A finder wraps the loader of every module the policy names as a target.
The module object exists at once and runs its code on the first
attribute fetch. A finder sees no importer, so a policy that asks about
importers picks nothing here. Expected weaker than the rewrites:
`from m import name` fetches at once, and `import a.b` needs `a` loaded
to find `b`.
"""

from __future__ import annotations

import importlib.machinery
import importlib.util
import sys
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ..policy import Policy

AVAILABLE = True

STATS = {"lazy": 0}

_NEVER = ("lazylab", "importlib", "encodings", "threading")


class _LazyFinder:
    _lazylab = True

    def __init__(self, policy: Policy):
        self.policy = policy

    def find_spec(self, fullname, path, target=None):
        if fullname.partition(".")[0] in _NEVER or not self.policy(None, fullname, None):
            return None
        spec = importlib.machinery.PathFinder.find_spec(fullname, path, target)
        if spec is None or type(spec.loader) is not importlib.machinery.SourceFileLoader:
            return spec
        spec.loader = importlib.util.LazyLoader(spec.loader)
        STATS["lazy"] += 1
        return spec

    def invalidate_caches(self):
        importlib.machinery.PathFinder.invalidate_caches()


def install(policy: Policy) -> None:
    sys.meta_path.insert(0, _LazyFinder(policy))
