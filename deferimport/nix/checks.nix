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
in
{
  unit = suite {
    name = "deferimport-unit";
    inputs = [ testEnv ];
    env = { inherit selection; };
    setup = prepare;
  } "python -m pytest $selection -q -p no:cacheprovider";

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
