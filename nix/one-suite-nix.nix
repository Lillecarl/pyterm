# Every source's `nix/suite.nix` is the same file, and this says so.
#
# There are seven copies, one per source, and they are byte for byte the
# same. They exist because a source has to stand alone: each is an
# ordinary clone with its own `default.nix`, buildable with no umbrella,
# so it cannot import a file from a sibling checkout by path.
#
# **The cost is that a change to the rule is a change to seven files**,
# and the copies can drift without anything noticing. Landing the
# `couldNotRun` rule met that: one copy changed, the derivation that was
# supposed to fail built happily, because each source reads its own copy.
#
# This is not the fix. Lillecarl/pymux#367 is the question of where the
# file should live, and it is shape. This turns a silent drift into a red
# gate in the meantime, and one edit undoes it.
{
  callPackage,
  sources,
}:
let
  # Any of the seven would do, and this check is what says so. pyte's is
  # the one the header of each copy and `CLAUDE.md` both point at.
  inherit (callPackage "${sources.pyte}/nix/suite.nix" { }) suite;

  # Named rather than taken from `sources` wholesale: `pyproject-nix` and
  # `umbrella` are in there too and neither has one of these.
  named = [
    "prompt-toolkit"
    "ptterm"
    "ptyhost"
    "pymux"
    "pyte"
    "pyterm-pytest"
    "txterm"
  ];

  copies = map (name: {
    inherit name;
    path = "${sources.${name}}/nix/suite.nix";
  }) named;

  first = builtins.head copies;
in
suite { name = "pyterm-one-suite-nix"; } ''
  drifted=0
  ${builtins.concatStringsSep "\n" (
    map (one: ''
      if cmp -s ${first.path} ${one.path}; then
        echo "${one.name}: the same"
      else
        echo "${one.name}: DIFFERS from ${first.name}"
        diff -u ${first.path} ${one.path} || true
        drifted=1
      fi
    '') (builtins.tail copies)
  )}

  if [ "$drifted" != "0" ]; then
    echo ""
    echo "The ${toString (builtins.length copies)} copies have to stay the same file."
    echo "Lillecarl/pymux#367 is where they should live instead."
    exit 1
  fi

  echo ""
  echo "nix/suite.nix is the same file in all ${toString (builtins.length copies)} sources."
''
