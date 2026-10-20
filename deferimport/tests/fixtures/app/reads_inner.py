"Reads `pkg_two.inner` off the package, trusting another module imported it, as pymux reads `anyio.to_thread`."

from __future__ import annotations

import app.uses_inner
import pkg_two


def read():
    return pkg_two.inner.VALUE
