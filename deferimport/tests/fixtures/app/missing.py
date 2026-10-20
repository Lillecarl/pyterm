from __future__ import annotations

import missing_mod
from heavy import not_there


def use_module():
    return missing_mod.value


def use_member():
    return not_there()
