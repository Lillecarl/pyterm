from __future__ import annotations

import plugins.one  # noqa: F401  (registers itself)
from plugins import REGISTRY


def registered():
    return sorted(REGISTRY)
