"Fails the first time it is imported in a process, as a module whose first import loses a race does."

import os

_SEEN = "DEFERIMPORT_TEST_FLAKY_SEEN"

if not os.environ.get(_SEEN):
    os.environ[_SEEN] = "1"
    raise RuntimeError("the first import fails")

VALUE = "second time"
