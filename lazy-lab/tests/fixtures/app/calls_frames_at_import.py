"Calls a frame-reading callee from its module body, as anyio calls its lazy importer."

from __future__ import annotations

from frames import caller

CALLER = caller()
