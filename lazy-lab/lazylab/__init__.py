"""
A temporary lab: every way to make plain imports lazy at import time,
tested against each other and measured. `README.md` says what it found.
"""

from __future__ import annotations

from . import hook
from .candidates import CANDIDATES, available, dunder_import, lazy_loader, native_filter
from .policy import Policy, parse

__all__ = ["Policy", "available", "install", "lazy_count", "parse"]


def install(candidate: str, policy: Policy | str) -> None:
    if isinstance(policy, str):
        policy = parse(policy)
    ok, installer = CANDIDATES[candidate]
    if not ok:
        raise RuntimeError("%s does not run on this interpreter" % candidate)
    installer(policy)


def lazy_count() -> int:
    "How many imports the installed candidate made lazy so far."
    return hook.STATS["lazy"] + native_filter.STATS["lazy"] + lazy_loader.STATS["lazy"] + dunder_import.STATS["lazy"]
