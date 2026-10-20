"""
Every way the lab makes an import lazy, by name.

| name | mechanism | interpreter |
| --- | --- | --- |
| `eager` | nothing: the baseline | any |
| `ast-native` | loader sets `is_lazy` on the AST | 3.15 |
| `ast-proxy` | loader rewrites to proxy assignments | any |
| `ast-proxy-restore` | the same, module class put back | any |
| `ast-proxy-loads` | the same, and a bare read of a lazy global resolves it | any |
| `ast-proxy-flags` | the same, with a flag per name that skips the call once resolved | any |
| `native-filter` | `sys.set_lazy_imports("all")` + filter | 3.15 |
| `lazy-loader` | `importlib.util.LazyLoader` per target | any |
| `dunder-import` | `builtins.__import__` returns proxies | any |
| `deferimport` | the source the winners became: native on 3.15, flags on 3.14 | any, when on the path |
"""

from __future__ import annotations

import importlib
import importlib.util
import os
from typing import TYPE_CHECKING

from . import ast_native, ast_proxy, dunder_import, lazy_loader, native_filter

if TYPE_CHECKING:
    from collections.abc import Callable

    from ..policy import Policy

__all__ = ["CANDIDATES", "available"]


def _eager(policy: Policy) -> None:
    pass


def _deferimport(policy: Policy) -> None:
    # The source the lab's winners became, judged the same way. Imported
    # here because only the measurements put it on the path.
    deferimport = importlib.import_module("deferimport")
    deferimport.install(policy.spec(), cache=os.environ.get("LAZYLAB_CACHE") or None)


CANDIDATES: dict[str, tuple[bool, Callable[[Policy], None]]] = {
    "eager": (True, _eager),
    "ast-native": (ast_native.AVAILABLE, ast_native.install),
    "ast-proxy": (ast_proxy.AVAILABLE, ast_proxy.install),
    "ast-proxy-restore": (ast_proxy.AVAILABLE, lambda policy: ast_proxy.install(policy, restore=True)),
    "ast-proxy-loads": (ast_proxy.AVAILABLE, lambda policy: ast_proxy.install(policy, loads=True)),
    "ast-proxy-flags": (ast_proxy.AVAILABLE, lambda policy: ast_proxy.install(policy, flags=True)),
    "native-filter": (native_filter.AVAILABLE, native_filter.install),
    "lazy-loader": (lazy_loader.AVAILABLE, lazy_loader.install),
    "dunder-import": (dunder_import.AVAILABLE, dunder_import.install),
    "deferimport": (importlib.util.find_spec("deferimport") is not None, _deferimport),
}


def available() -> list[str]:
    "The candidates this interpreter can run."
    return [name for name, (ok, _) in CANDIDATES.items() if ok]
