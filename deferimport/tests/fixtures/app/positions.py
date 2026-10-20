"""
Every position 3.15's global mode treats differently. Each imports a
module nothing else loads: a lazy `from m import x` binds eagerly on
3.15 when `m` is already in `sys.modules`, which would hide the rule.
"""

from __future__ import annotations

import marks.plain as top_plain
from marks.from_ import VALUE as top_from

if True:
    from marks.if_ import VALUE as in_if
try:
    from marks.try_ import VALUE as in_try
except ImportError:
    in_try = None
with open(__file__):
    from marks.with_ import VALUE as in_with
for _ in [1]:
    from marks.for_ import VALUE as in_for
while True:
    from marks.while_ import VALUE as in_while

    break
match 1:
    case 1:
        from marks.match_ import VALUE as in_match


class Holder:
    from marks.class_ import VALUE as in_class


def function():
    from marks.def_ import VALUE as in_def

    return in_def
