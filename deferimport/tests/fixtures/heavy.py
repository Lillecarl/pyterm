"""
The module every probe wants to defer. It says when its code ran:
`LazyLoader` puts a module in `sys.modules` before that.
"""

import os
import time

os.environ["DEFERIMPORT_TEST_HEAVY_RAN"] = "1"

NAME = "heavy"
COUNT = 0


class Thing:
    pass


class Boom(Exception):
    pass


def raise_boom():
    raise Boom("boom")


def deco(function):
    return function


if os.environ.get("DEFERIMPORT_TEST_SLOW_HEAVY"):
    # Wide enough for a second thread to arrive during the import.
    time.sleep(0.2)
