"""
A stand-in for a module or a member, imported on first use.

Lifted from the `lazy-imports` branch's `_lazy_shim.py`, without the
token parser: here the AST rewrite in `candidates/ast_proxy.py` emits
the calls to `lazy_mod`, `lazy_mod_as` and `lazy_from`.

A proxy rebinds the name it was bound to once it resolves, so after the
first use a global read is the real object and costs nothing. What
still costs is the module: an outside `mod.name` must resolve a proxy it
finds, which needs a `__getattribute__` written in Python on the
module's class. `LazyModuleType` is that class, and `RESTORE` decides
whether a module goes back to `types.ModuleType` once its last proxy
resolves. The two are measured against each other.
"""

from __future__ import annotations

import copy
import importlib
import sys
import threading
import types
from typing import Any

__all__ = ["LazyModuleType", "LazyProxy", "lazy_from", "lazy_mod", "lazy_mod_as"]

#: The global a rewritten module counts its unresolved proxies in.
PENDING = "__lazylab_pending__"

#: Whether a module drops `LazyModuleType` once nothing in it is pending.
#: Set by the candidate that installs the hook.
RESTORE = False

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


class LazyModuleType(types.ModuleType):
    "Resolves a proxy on attribute fetch, as 3.15 does for a lazy global."

    def __getattribute__(self, name):
        value = object.__getattribute__(self, name)
        if type(value) is LazyProxy:
            return value._reify()
        return value


#: The global that holds a module's own class, when it has one.
CLASS = "__lazylab_class__"

#: Set in a module whose reads test a flag per name (`loads.done`).
FLAGS = "__lazylab_flags__"


def done(name: str) -> str:
    "The flag global of `name`. The same spelling `loads.done` emits."
    return "__lazylab_done_%s__" % name


def own_class(module: types.ModuleType) -> type:
    """
    Give `module` a class of its own, which holds a property for each
    name still lazy. An outside fetch of that name resolves it, and the
    property goes once it has; every other fetch never leaves C. The
    other way, `LazyModuleType`, runs `__getattribute__` in Python on
    every fetch from outside, for as long as the module lives.
    """
    cls = type("LazyModule", (types.ModuleType,), {})
    module.__class__ = cls
    module.__dict__[CLASS] = cls
    return cls


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


def _resolved_one(namespace: dict) -> None:
    pending = namespace.get(PENDING, 0) - 1
    namespace[PENDING] = pending
    if pending > 0 or not RESTORE:
        return
    module = sys.modules.get(namespace.get("__name__", ""))
    if module is not None and type(module) is LazyModuleType and module.__dict__ is namespace:
        module.__class__ = types.ModuleType


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
        if namespace is not None:
            namespace[PENDING] = namespace.get(PENDING, 0) + 1
            cls = namespace.get(CLASS)
            if cls is not None and name:
                setattr(cls, name, _descriptor(name))
            if name and namespace.get(FLAGS):
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
                exc.add_note(f"lazy import declared at {self._lazy_site}")
                raise
            finally:
                self._lazy_by = None
            self._lazy_obj = obj
            self._lazy_done = True
            namespace = self._lazy_namespace
            if namespace is not None:
                # Only while the name still holds this proxy: the module
                # may have rebound it since. With no name, as for a
                # proxy `__import__` returned, every name holding it.
                names = [self._lazy_name] if self._lazy_name else [k for k, v in namespace.items() if v is self]
                for name in names:
                    if namespace.get(name) is self:
                        namespace[name] = obj
                        _forget(namespace, name)
                        if namespace.get(FLAGS):
                            namespace[done(name)] = True
                _resolved_one(namespace)
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
        # A class statement with a proxy among its bases. A base that is
        # not a class answers for itself: `typing.NamedTuple` is a
        # function whose own `__mro_entries__` names the real base.
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
    otherwise `a.b` is missing once `a` resolves. With no `name`, the
    proxy rebinds whatever holds it, and merges with what `a` holds.
    """
    top = fullname.partition(".")[0]
    before = namespace.get(name or top) if namespace is not None else None
    if type(before) is not LazyProxy or object.__getattribute__(before, "_lazy_done"):
        before = None

    def resolve():
        if before is not None:
            before._reify()
        importlib.import_module(fullname)
        return sys.modules[top]

    return LazyProxy(resolve, site, namespace, name, fullname)


def lazy_mod_as(namespace, name, fullname, site):
    "Bind `import a.b as c`, or `import a`, to the module itself."
    return LazyProxy(lambda: importlib.import_module(fullname), site, namespace, name, fullname)


def lazy_from(namespace, name, target, attr, site):
    "Bind one name of `from target import attr`."
    display = f"{target}.{attr}"

    def resolve():
        module = importlib.import_module(target)
        try:
            return getattr(module, attr)
        except AttributeError:
            pass
        fullname = f"{target}.{attr}"
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

    return LazyProxy(resolve, site, namespace, name, display)
