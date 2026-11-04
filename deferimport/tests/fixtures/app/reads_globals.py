"""
Reads its own globals at import, the way `symtable` builds `_flags`
from `globals().items()`.
"""

from heavy import COUNT, NAME

CONSTANTS = [value for key, value in globals().items() if key.isupper()]


def constant_types():
    return [type(value).__name__ for value in CONSTANTS]


def masked():
    "What `symtable` does with a flag from `_flags`: `int & flag`."
    return 7 & CONSTANTS[0]


def counts():
    return COUNT + 1
