from __future__ import annotations

import pkg_two.inner
import pkg_two.other


def both():
    return pkg_two.inner.VALUE, pkg_two.other.VALUE
