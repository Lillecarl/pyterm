from __future__ import annotations

from heavy import NAME, Boom, Thing, raise_boom


def make():
    return Thing()


def is_thing(value):
    return isinstance(value, Thing)


def is_subclass(cls):
    return issubclass(cls, Thing)


def raw():
    return Thing


def catch():
    try:
        raise_boom()
    except Boom:
        return "caught"


def formatted():
    return f"{NAME}!"


def concatenated():
    return NAME + "!"


def matched(value):
    match value:
        case Thing():
            return "a Thing"
        case _:
            return "something else"
