"""
Make plain imports lazy at import time: no `lazy` keyword in the source.

    import deferimport
    deferimport.install("deny=hypothesis,asyncssh")

`install` puts a finder first on `sys.meta_path`. In every module loaded
after it, whoever imports it and however, each module-scope import the
policy picks goes lazy, in the positions 3.15 picks itself. So the
laziness cascades through every dependency, where the `lazy` keyword
makes one statement lazy and leaves what that module imports eager.

The mechanism follows the interpreter:

- 3.15 has lazy imports of its own: the loader sets `__lazy_modules__`
  to an object that asks the policy, and rewrites nothing.
- 3.14 has none, so each import becomes a proxy, and the reads a proxy
  would leak are rewritten to resolve it. A first call from inside a
  function to a callee that reads its caller's frame sees the proxy as
  that caller; nothing else does.

`DEFERIMPORT=eager` in the environment makes `install` do nothing, so
one suite runs both ways. What may not go lazy: an import made for what
it does (a module that registers itself) and a module that replaces
itself in `sys.modules`. Deny those.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Literal

from . import hook
from .native import Native
from .policy import Policy, parse
from .rewrite import Proxies

__all__ = ["NATIVE", "Policy", "install", "installed", "parse"]

#: Whether this interpreter has lazy imports of its own (PEP 810).
NATIVE = sys.version_info >= (3, 15)

Mechanism = Literal["native", "proxies"]


def installed() -> hook.Finder | None:
    "The finder `install` put on `sys.meta_path`, if it did."
    return next((finder for finder in sys.meta_path if isinstance(finder, hook.Finder)), None)


def install(
    policy: Policy | str = "everything",
    *,
    mechanism: Mechanism | None = None,
    cache: os.PathLike | str | None = None,
) -> hook.Finder | None:
    """
    Rewrite every module loaded from now on, as `policy` says.

    `mechanism` picks one by hand, for a test: "proxies" runs on 3.15
    too. `cache` is where the rewritten bytecode goes; by default
    `DEFERIMPORT_CACHE`, or the user's cache directory. Installing twice
    gives back the first finder. Returns None when `DEFERIMPORT=eager`.
    """
    if os.environ.get("DEFERIMPORT") == "eager":
        return None
    existing = installed()
    if existing is not None:
        return existing
    if isinstance(policy, str):
        policy = parse(policy)
    if mechanism is None:
        mechanism = "native" if NATIVE else "proxies"
    if mechanism == "native" and not NATIVE:
        raise RuntimeError("lazy imports of the interpreter's own need 3.15")
    transform: hook.Transform = Native(policy) if mechanism == "native" else Proxies()
    return hook.install(transform, policy, hook.cache_directory() if cache is None else Path(cache))
