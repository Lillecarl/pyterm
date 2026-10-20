"""
3.14: a stand-in for a module or a member, imported on first use.

A proxy rebinds the name it was bound to once it resolves, so after its
first use a read of that name is the real object. Three things make
that hold where 3.15 holds it in C:

- `rewrite.py` turns every read the proxy would leak into a resolving
  one: a bare read, and a call in a module or class body.
- A module that holds a proxy gets a class of its own, with a property
  per name still lazy, so a fetch from outside resolves it. The property
  goes once the name resolves, and every other fetch stays in C. The
  other way, a module class with a Python `__getattribute__`, cost a
  frame of pymux 8% and skipped a module's own `__getattr__`.
- `submodules.py` keeps a lazily imported submodule reachable from its
  package.
"""

from __future__ import annotations

import copy
import importlib
import sys
import threading
import types
from typing import Any

from . import submodules

__all__ = ["LazyProxy", "done", "keep_class", "lazy_from", "lazy_mod", "lazy_mod_as", "own_class"]

#: The global that holds a module's own class.
CLASS = "__deferimport_class__"

#: Set in a module whose reads test a flag per name.
FLAGS = "__deferimport_flags__"

_STATE = frozenset(
    (
        "_lazy_resolve",
        "_lazy_site",
        "_lazy_lock",
        "_lazy_obj",
        "_lazy_done",
        "_lazy_by",
        "_lazy_namespace",
        "_lazy_name",
        "_lazy_display",
        "_reify",
        # A class statement looks this up on the base itself, not its type.
        "__mro_entries__",
    )
)


def done(name: str) -> str:
    "The flag global that says `name` holds its real object."
    return "__deferimport_done_%s__" % name


def own_class(module: types.ModuleType) -> type:
    "Give `module` a class of its own, for the properties of its lazy names."
    cls = type("DeferredModule", (type(module),), {})
    module.__class__ = cls
    module.__dict__[CLASS] = cls
    return cls


def keep_class(module: types.ModuleType) -> None:
    """
    After the module ran: if it gave itself a class of its own, as some
    modules do, derive one from that with the properties still pending.
    """
    cls = module.__dict__.get(CLASS)
    if cls is None or isinstance(module, cls):
        return
    pending = {name: value for name, value in cls.__dict__.items() if isinstance(value, property)}
    replacement = type("DeferredModule", (type(module),), pending)
    module.__class__ = replacement
    module.__dict__[CLASS] = replacement


def _forget(namespace: dict, name: str) -> None:
    cls = namespace.get(CLASS)
    if cls is not None and isinstance(cls.__dict__.get(name), property):
        delattr(cls, name)


def _descriptor(name: str) -> property:
    def get(module):
        value = module.__dict__[name]
        if type(value) is LazyProxy:
            return value._reify()
        _forget(module.__dict__, name)
        return value

    def set_(module, value):
        module.__dict__[name] = value
        _forget(module.__dict__, name)

    def delete(module):
        del module.__dict__[name]
        _forget(module.__dict__, name)

    return property(get, set_, delete)


class LazyProxy:
    __slots__ = (
        "_lazy_by",
        "_lazy_display",
        "_lazy_done",
        "_lazy_lock",
        "_lazy_name",
        "_lazy_namespace",
        "_lazy_obj",
        "_lazy_resolve",
        "_lazy_site",
    )

    def __init__(self, resolve, site, namespace, name, display):
        self._lazy_resolve = resolve
        self._lazy_site = site
        self._lazy_lock = threading.Lock()
        self._lazy_obj = None
        self._lazy_done = False
        self._lazy_by = None
        self._lazy_namespace = namespace
        self._lazy_name = name
        self._lazy_display = display
        cls = namespace.get(CLASS)
        if cls is not None:
            setattr(cls, name, _descriptor(name))
        if namespace.get(FLAGS):
            namespace[done(name)] = False

    def _reify(self) -> Any:
        if self._lazy_done:
            return self._lazy_obj
        ident = threading.get_ident()
        if self._lazy_by == ident:
            raise ImportError(f"cannot import name {self._lazy_display!r} (most likely due to a circular import)")
        with self._lazy_lock:
            if self._lazy_done:
                return self._lazy_obj
            self._lazy_by = ident
            try:
                obj = self._lazy_resolve()
            except Exception as exc:
                # Nothing is kept: the next use tries again, as on 3.15.
                exc.add_note(f"lazy import declared at {self._lazy_site}")
                raise
            finally:
                self._lazy_by = None
            self._lazy_obj = obj
            self._lazy_done = True
            namespace = self._lazy_namespace
            name = self._lazy_name
            now = namespace.get(name)
            # Only while the name still holds this proxy: the module may
            # have rebound it since. Or while it holds the submodule of
            # that name, which the import just set on its package:
            # eagerly, the statement runs after that and wins
            # (cryptography's `openssl.backend` is an object and a module).
            if now is self or (now is not obj and now is sys.modules.get("%s.%s" % (namespace.get("__name__"), name))):
                namespace[name] = obj
                _forget(namespace, name)
                if namespace.get(FLAGS):
                    namespace[done(name)] = True
            return obj

    def __getattribute__(self, name):
        if name in _STATE:
            return object.__getattribute__(self, name)
        return getattr(self._reify(), name)

    def __setattr__(self, name, value):
        if name in _STATE:
            object.__setattr__(self, name, value)
        else:
            setattr(self._reify(), name, value)

    def __delattr__(self, name):
        if name in _STATE:
            object.__delattr__(self, name)
        else:
            delattr(self._reify(), name)

    def __repr__(self):
        done = object.__getattribute__(self, "_lazy_done")
        site = object.__getattribute__(self, "_lazy_site")
        return f"<lazy {site} ({'imported' if done else 'not yet imported'})>"

    def __str__(self):
        return repr(self)

    def __dir__(self):
        return dir(self._reify())

    def __call__(self, *args, **kwargs):
        return self._reify()(*args, **kwargs)

    def __bool__(self):
        return bool(self._reify())

    def __len__(self):
        return len(self._reify())

    def __iter__(self):
        return iter(self._reify())

    def __aiter__(self):
        return self._reify().__aiter__()

    def __contains__(self, item):
        return item in self._reify()

    def __getitem__(self, key):
        return self._reify()[key]

    def __eq__(self, other):
        return self._reify() == other

    def __ne__(self, other):
        return self._reify() != other

    def __hash__(self):
        return hash(self._reify())

    def __instancecheck__(self, instance):
        return isinstance(instance, self._reify())

    def __subclasscheck__(self, subclass):
        return issubclass(subclass, self._reify())

    def __mro_entries__(self, bases):
        # A base that is not a class answers for itself: `typing.NamedTuple`
        # is a function whose own `__mro_entries__` names the real base.
        real = self._reify()
        if not isinstance(real, type) and hasattr(real, "__mro_entries__"):
            return real.__mro_entries__(bases)
        return (real,)

    def __lt__(self, other):
        return self._reify() < other

    def __le__(self, other):
        return self._reify() <= other

    def __gt__(self, other):
        return self._reify() > other

    def __ge__(self, other):
        return self._reify() >= other

    def __add__(self, other):
        return self._reify() + other

    def __radd__(self, other):
        return other + self._reify()

    def __sub__(self, other):
        return self._reify() - other

    def __rsub__(self, other):
        return other - self._reify()

    def __mul__(self, other):
        return self._reify() * other

    def __rmul__(self, other):
        return other * self._reify()

    def __truediv__(self, other):
        return self._reify() / other

    def __rtruediv__(self, other):
        return other / self._reify()

    def __floordiv__(self, other):
        return self._reify() // other

    def __rfloordiv__(self, other):
        return other // self._reify()

    def __mod__(self, other):
        return self._reify() % other

    def __rmod__(self, other):
        return other % self._reify()

    def __pow__(self, other):
        return self._reify() ** other

    def __rpow__(self, other):
        return other ** self._reify()

    def __and__(self, other):
        return self._reify() & other

    def __rand__(self, other):
        return other & self._reify()

    def __or__(self, other):
        return self._reify() | other

    def __ror__(self, other):
        return other | self._reify()

    def __xor__(self, other):
        return self._reify() ^ other

    def __rxor__(self, other):
        return other ^ self._reify()

    def __lshift__(self, other):
        return self._reify() << other

    def __rlshift__(self, other):
        return other << self._reify()

    def __rshift__(self, other):
        return self._reify() >> other

    def __rrshift__(self, other):
        return other >> self._reify()

    def __neg__(self):
        return -self._reify()

    def __pos__(self):
        return +self._reify()

    def __abs__(self):
        return abs(self._reify())

    def __invert__(self):
        return ~self._reify()

    def __int__(self):
        return int(self._reify())

    def __float__(self):
        return float(self._reify())

    def __complex__(self):
        return complex(self._reify())

    def __index__(self):
        return self._reify().__index__()

    def __enter__(self):
        return self._reify().__enter__()

    def __exit__(self, *args):
        return self._reify().__exit__(*args)

    def __await__(self):
        return self._reify().__await__()

    def __copy__(self):
        return copy.copy(self._reify())

    def __deepcopy__(self, memo):
        return copy.deepcopy(self._reify(), memo)

    def __reduce__(self):
        return self._reify().__reduce__()


def lazy_mod(namespace, name, fullname, site):
    """
    Bind the top name of `import a.b.c`. A second `import a.d` binds `a`
    again, and its proxy imports what the first one would have too:
    otherwise `a.b` is missing once `a` resolves.
    """
    top = fullname.partition(".")[0]
    before = namespace.get(name)
    if type(before) is not LazyProxy or object.__getattribute__(before, "_lazy_done"):
        before = None

    def resolve():
        if before is not None:
            before._reify()
        importlib.import_module(fullname)
        return sys.modules[top]

    submodules.register_dotted(fullname)
    return LazyProxy(resolve, site, namespace, name, fullname)


def lazy_mod_as(namespace, name, fullname, site):
    "Bind `import a.b as c`, or `import a`, to the module itself."
    submodules.register_dotted(fullname)
    return LazyProxy(lambda: importlib.import_module(fullname), site, namespace, name, fullname)


def lazy_from(namespace, name, target, attr, site):
    "Bind one name of `from target import attr`."
    submodules.register_dotted(target)
    submodules.register(target, attr)
    made: list[LazyProxy] = []

    def resolve():
        module = importlib.import_module(target)
        fullname = f"{target}.{attr}"
        # `from . import sub` in a package binds the proxy in the very
        # namespace it fetches from: the fetch would find itself and
        # report a cycle. multiprocessing does this. The submodule is
        # what such a name means.
        if getattr(module, "__dict__", {}).get(attr) is made[0]:
            return importlib.import_module(fullname)
        try:
            return getattr(module, attr)
        except AttributeError:
            pass
        try:
            return importlib.import_module(fullname)
        except ModuleNotFoundError as exc:
            if exc.name != fullname:
                raise
        spec = getattr(module, "__spec__", None)
        if getattr(spec, "_initializing", False):
            raise ImportError(
                f"cannot import name {attr!r} from partially initialized module"
                f" {target!r} (most likely due to a circular import)"
            ) from None
        path = getattr(module, "__file__", None)
        where = f" from {target!r} ({path})" if path else f" from {target!r}"
        raise ImportError(f"cannot import name {attr!r}{where}") from None

    made.append(LazyProxy(resolve, site, namespace, name, f"{target}.{attr}"))
    return made[0]
