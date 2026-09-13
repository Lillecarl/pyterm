# Every source this collection uses, named once.
#
# The umbrella owns them. None of the repositories here is a flake, so none
# of them resolves anything of its own: each takes this set and imports what
# it wants.
#
# Two files make it, and each has one writer:
#
#   nix/sources.nix   where a source comes from. A human writes it.
#   nix/sources.lock  which revision. A tool writes it.
#
# nix/resolve.nix joins them. Read those three files, not this one.
#
# A value here is a path or a flake reference string, which is what
# nix/fetch.nix turns into one directory. A caller that wants directories
# asks nix/wire.nix.
import ./resolve.nix {
  spec = import ./sources.nix;
  lock = builtins.fromJSON (builtins.readFile ./sources.lock);
}
