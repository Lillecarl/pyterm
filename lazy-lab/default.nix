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
  # pymux's dev environment on each of them, by the same names: what the
  # measurements import.
  devEnvs,
}:
let
  inherit (callPackage (sources.pyte + "/nix/suite.nix") { }) suite;

  src = lib.fileset.toSource {
    root = ./.;
    fileset = lib.fileset.unions [
      ./lazylab
      ./measure
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

  # Every workload under every candidate and policy: `$out/report.md`.
  # Not a verdict on anything; the report is the result, and its
  # clock column belongs to a sandbox beside other jobs.
  measure =
    version: devEnv:
    suite {
      name = "lazy-lab-measure-${version}";
      inputs = [ devEnv ];
      setup = ''
        cp -r ${src} lab
        cp -r ${sources.pymux}/tests pymux-tests
        chmod -R +w lab pymux-tests
        # The source the lab's winners became, beside the lab on its path.
        cp -r ${sources.deferimport}/deferimport lab/deferimport
        export HOME="$TMPDIR"
        export LANG=C.UTF-8
      '';
    } "python lab/measure/report.py $out $PWD/pymux-tests";

  # pymux's unit suite eager and under each candidate, and what each
  # adds to the eager failures: `$out/report.md`. Minutes per
  # candidate, so narrow it while hunting:
  #
  #     LAZYLAB_PYMUX_CANDIDATES=ast-native LAZYLAB_PYMUX_POLICIES=everything \
  #       nix build --file . checks.lazy-lab-pymux-unit-315.run
  pymuxCandidates = builtins.getEnv "LAZYLAB_PYMUX_CANDIDATES";
  pymuxPolicies = builtins.getEnv "LAZYLAB_PYMUX_POLICIES";
  pymuxTests = builtins.getEnv "LAZYLAB_PYMUX_TESTS";
  pymuxUnit =
    version: devEnv:
    suite {
      name = "lazy-lab-pymux-unit-${version}";
      inputs = [ devEnv ];
      env = {
        LAZYLAB_PYMUX_CANDIDATES = pymuxCandidates;
        LAZYLAB_PYMUX_POLICIES = pymuxPolicies;
        LAZYLAB_PYMUX_TESTS = pymuxTests;
      };
      setup = ''
        cp -r ${src} lab
        mkdir pymux-source
        cp -r ${sources.pymux}/pymux ${sources.pymux}/tests ${sources.pymux}/pyproject.toml pymux-source
        chmod -R +w lab pymux-source
        cp -r ${sources.deferimport}/deferimport lab/deferimport
        export HOME="$TMPDIR"
        export LANG=C.UTF-8
      '';
    } "python lab/measure/pymux_unit.py $out $PWD/pymux-source";
in
lib.mapAttrs' (version: python: lib.nameValuePair "lazy-lab-unit-${version}" (unit version python)) pythons
// lib.mapAttrs' (version: devEnv: lib.nameValuePair "lazy-lab-measure-${version}" (measure version devEnv)) devEnvs
// lib.mapAttrs' (version: devEnv: lib.nameValuePair "lazy-lab-pymux-unit-${version}" (pymuxUnit version devEnv)) devEnvs
