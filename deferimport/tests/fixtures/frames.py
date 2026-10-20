"A callee that reads its caller's frame, as anyio's lazy importer and `warnings` do."

import sys


def caller():
    return sys._getframe(1).f_globals.get("__name__")
