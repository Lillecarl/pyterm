# prompt-toolkit's `nix/suite.nix` is the root's `nix/shared/suite.nix`.
#
# Every source holds a copy, because a source has to stand alone: josh
# exports each one as its own repository, so it cannot import a file of a
# sibling by path. `sync-sources` writes the copies of this repository's
# sources, and `checks.pyterm-sources-in-step` holds them. prompt-toolkit
# is a fork with a repository of its own, so sync writes nothing there, and
# this is the check that its copy has not drifted. Lillecarl/pymux#367.
{
  callPackage,
  sources,
}:
let
  inherit (callPackage ./shared/suite.nix { }) suite;

  # A path joined and not interpolated: a source in this tree is a path,
  # and "${path}" copies its whole directory, caches and all, to the store.
  copy = sources.prompt-toolkit + "/nix/suite.nix";
in
suite { name = "pyterm-one-suite-nix"; } ''
  if ! cmp -s ${./shared/suite.nix} ${copy}; then
    echo "prompt-toolkit's nix/suite.nix differs from nix/shared/suite.nix:"
    diff -u ${./shared/suite.nix} ${copy} || true
    echo "Change it in the fork as well, then move the pin."
    exit 1
  fi
  echo "prompt-toolkit's nix/suite.nix is the root's."
''
