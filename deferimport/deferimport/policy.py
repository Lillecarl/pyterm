"""
Which imports go lazy, as one function.

The shape is the one `sys.set_lazy_imports_filter` calls on 3.15:
`(importer, target, fromlist) -> bool`, where `target` is the resolved
absolute name and `fromlist` is `None` for a plain `import`.

A policy is also a string, which is how it travels in
`DEFERIMPORT_POLICY` to the pytest plugin:

    everything
    importers=pymux,ptterm
    deny=hypothesis,asyncssh
    importers=pymux;deny=pymux.commands

Prefixes match a dotted name and everything under it. Two kinds of
import want a deny: one made for what it does (a module that registers
itself), and one whose module replaces itself in `sys.modules`.
"""

from __future__ import annotations

from dataclasses import dataclass, field

__all__ = ["Policy", "parse"]


def _under(name: str | None, prefixes: frozenset[str]) -> bool:
    if name is None:
        return False
    return any(name == prefix or name.startswith(prefix + ".") for prefix in prefixes)


@dataclass(frozen=True)
class Policy:
    #: Only imports made by modules under these go lazy. Empty means any.
    importers: frozenset[str] = field(default_factory=frozenset)
    #: Only imports of modules under these go lazy. Empty means any.
    targets: frozenset[str] = field(default_factory=frozenset)
    #: Never lazy, whoever imports it.
    deny: frozenset[str] = field(default_factory=frozenset)

    def __call__(self, importer: str | None, target: str, fromlist: tuple[str, ...] | None = None) -> bool:
        if _under(target, self.deny):
            return False
        # `from pkg import sub` may name a submodule, and denying `pkg.sub`
        # has to catch that spelling too.
        if fromlist and any(_under(f"{target}.{name}", self.deny) for name in fromlist):
            return False
        if self.importers and not _under(importer, self.importers):
            return False
        return not (self.targets and not _under(target, self.targets))

    def covers_importer(self, importer: str) -> bool:
        "Whether a module's own imports may be rewritten at all."
        return not self.importers or _under(importer, self.importers)

    def spec(self) -> str:
        parts = [
            "%s=%s" % (key, ",".join(sorted(value)))
            for key, value in (("importers", self.importers), ("targets", self.targets), ("deny", self.deny))
            if value
        ]
        return ";".join(parts) or "everything"


def parse(spec: str) -> Policy:
    if spec.strip() in ("", "everything"):
        return Policy()
    fields: dict[str, frozenset[str]] = {}
    for part in spec.split(";"):
        key, _, value = part.partition("=")
        key = key.strip()
        if key not in ("importers", "targets", "deny"):
            raise ValueError("unknown policy field %r in %r" % (key, spec))
        fields[key] = frozenset(name.strip() for name in value.split(",") if name.strip())
    return Policy(**fields)
