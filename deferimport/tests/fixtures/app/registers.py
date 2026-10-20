from __future__ import annotations

import plugins.one
from plugins import REGISTRY


def registered():
    return sorted(REGISTRY)
