# TEMPORARY: the lazy-import lab, and every check it has.
#
# Not a source: it has no `flake.nix`, so the josh export and
# `lock-subtrees` never see it, and the root keeps these checks out of
# `checks.all`. Delete this directory and its lines in the root
# `default.nix` once it has answered. `README.md` says what it asks.
{
  lib,
  callPackage,
  sources,
  # The interpreters the lab runs on, by a short name: `{ "314" = ...; }`.
  pythons,
}:
let
  inherit (callPackage (sources.pyte + "/nix/suite.nix") { }) suite;

  src = lib.fileset.toSource {
    root = ./.;
    fileset = lib.fileset.unions [
      ./lazylab
      ./tests
      ./pyproject.toml
    ];
  };

  # Narrow a run while hunting:
  #
  #     LAZYLAB_TESTS=tests/test_parity.py::test_probe nix build --file . checks.lazy-lab-unit-315
  selection = builtins.getEnv "LAZYLAB_TESTS";

  unit =
    version: python:
    suite {
      name = "lazy-lab-unit-${version}";
      inputs = [ (python.withPackages (p: [ p.pytest ])) ];
      env = { inherit selection; };
      setup = ''
        cp -r ${src}/. .
        chmod -R +w .
        export HOME="$TMPDIR"
      '';
    } "python -m pytest $selection -q -p no:cacheprovider";
in
lib.mapAttrs' (version: python: lib.nameValuePair "lazy-lab-unit-${version}" (unit version python)) pythons
