"An object whose `__del__` reads a lazy name only at interpreter exit."

import warnings


class Late:
    def __del__(self):
        warnings.warn("late", ResourceWarning, stacklevel=1)


kept = Late()
