"""
Which imports go lazy, as one function every candidate consumes.

The shape is the one `sys.set_lazy_imports_filter` calls on 3.15:
`(importer, target, fromlist) -> bool`, where `target` is the resolved
absolute name and `fromlist` is `None` for a plain `import`. A candidate
that cannot see the importer (a finder sees only the target) passes
`None` there, and a policy that asks about importers answers False.

A policy travels to a fresh interpreter as a string in `LAZYLAB_POLICY`:

    everything
    importers=pymux,ptterm
    importers=pymux;deny=pymux.commands
    targets=anyio,aiosqlite

Prefixes match a dotted name and everything under it. A name from
`PRESETS` stands for its spec.

A rewrite cascades: every module the hook loads is rewritten, so with
"everything" a lazy import's own imports are lazy too, down through the
standard library. 3.15's `lazy` keyword makes one statement lazy, and
what that module imports in turn stays eager.
"""

from __future__ import annotations

from dataclasses import dataclass, field

__all__ = ["PRESETS", "Policy", "parse"]

_OURS = "pymux,libpymux,ptterm,ptyhost,pyte,txterm,pyterm_pytest"

PRESETS = {
    # Every import our packages make, and none anybody else makes.
    "ours": "importers=" + _OURS,
    # Only our packages' imports of the rest of the world.
    "foreign": "importers=%s;deny=%s" % (_OURS, _OURS),
    # Every import in every module, down through the standard library.
    "everything": "everything",
    # "everything", but for the packages that register on import, which
    # pymux's suite found under it:
    # - hypothesis: `strategies/__init__` checks that every strategy it
    #   exports registered itself, and the modules that register have
    #   not run.
    # - asyncssh: `eddsa`, `rsa` and the rest register their key
    #   algorithms on import, so `ssh-ed25519` was unknown.
    "everything-but": "deny=hypothesis,asyncssh",
}


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
    #: Never lazy, whoever imports it: the import is wanted for what it does.
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
    spec = PRESETS.get(spec.strip(), spec)
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
