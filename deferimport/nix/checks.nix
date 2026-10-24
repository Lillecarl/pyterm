# The suites that judge deferimport.
#
# It declares its own inputs, so `default.nix` holds the package and carries
# nothing that only a test needs. `nix/suite.nix` says why a check is two
# derivations.
#
# The probes start a fresh interpreter each, under each mechanism this
# python runs: 3.15 runs the native one and the proxies, 3.14 the
# proxies. pyterm builds this check on both.
{
  testEnv,
  # The interpreter with the nixpkgs package of `python-package.nix`, the
  # one `overlay.nix` gives a project outside pyterm, and pytest.
  nixpkgsEnv,
  # The same, on each interpreter from the floor up to the collection's,
  # by version: "311".
  olderEnvs,
  lib,
  callPackage,
  testSources,
  ruff,
}:
let
  inherit (callPackage ./suite.nix { }) suite;

  # Narrow a run to one file or one test while hunting:
  #
  #     DEFERIMPORT_TESTS=tests/test_parity.py nix build --file . checks.deferimport-unit
  selection = builtins.getEnv "DEFERIMPORT_TESTS";

  prepare = ''
    cp -r ${testSources}/tests .
    cp ${testSources}/pyproject.toml .
    chmod -R +w .
    export HOME="$TMPDIR"
    export LANG=C.UTF-8
  '';

  pytest =
    name: env:
    suite {
      inherit name;
      inputs = [ env ];
      env = { inherit selection; };
      setup = prepare;
    } "python -m pytest $selection -q -p no:cacheprovider";
in
# The same suite on each older interpreter: `nixpkgs-311` and so on.
lib.mapAttrs' (
  version: env: lib.nameValuePair "nixpkgs-${version}" (pytest "deferimport-nixpkgs-${version}" env)
) olderEnvs
// {
  unit = pytest "deferimport-unit" testEnv;

  # The same suite against the package another project gets from
  # `overlay.nix`. The probes put only the tests on the path, so the
  # package they import is the installed one.
  nixpkgs = pytest "deferimport-nixpkgs" nixpkgsEnv;

  # The selected rules, the layout at width 120, and the future import in
  # every file but the fixtures, which are what the probes import and
  # are written to be awkward. `ruff.toml` in the pyterm root says what
  # each rule is for.
  ruff = suite {
    name = "deferimport-ruff";
    inputs = [ ruff ];
    setup = prepare + ''
      cp -r ${testSources}/deferimport .
    '';
  } ''
    export RUFF_CACHE_DIR="$TMPDIR/ruff"
    ruff check deferimport tests
    ruff format --check deferimport tests
    missing=$(grep -rL '^from __future__ import annotations' --include='*.py' --exclude-dir='.*' --exclude-dir='__pycache__' --exclude-dir='fixtures' deferimport tests || true)
    if [ -n "$missing" ]; then
      echo "files without the future import:"
      echo "$missing"
      exit 1
    fi
  '';
}
