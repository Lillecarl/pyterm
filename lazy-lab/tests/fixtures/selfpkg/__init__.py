"A package that imports its own submodule and uses it at once, as multiprocessing does."

from . import sub

VALUE = sub.VALUE
