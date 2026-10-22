# The suites that judge ptkhx.
#
# It declares its own inputs, so `default.nix` holds the package and carries
# nothing that only a test needs. `nix/suite.nix` says why a check is two
# derivations.
{
  testEnv,
  callPackage,
  testSources,
  ruff,
  helix,
}:
let
  inherit (callPackage ./suite.nix { }) suite;

  # Narrow a run to one file or one test while hunting:
  #
  #     PTKHX_TESTS=tests/test_keymap.py nix build --file . checks.ptkhx-unit
  selection = builtins.getEnv "PTKHX_TESTS";

  prepare = ''
    cp -r ${testSources}/tests .
    cp ${testSources}/pyproject.toml .
    chmod -R +w .
    export HOME="$TMPDIR"
    export LANG=C.UTF-8
  '';
in
{
  # The keymap against ptkhx alone.
  unit = suite {
    name = "ptkhx-unit";
    inputs = [ testEnv ];
    env = { inherit selection; };
    setup = prepare;
  } "python -m pytest $selection -q -p no:cacheprovider -m 'not oracle'";

  # The same cases, each run through real Helix on a pty as well, and
  # the two answers compared.
  oracle = suite {
    name = "ptkhx-oracle";
    inputs = [
      testEnv
      helix
    ];
    env = { inherit selection; };
    setup = prepare;
  } "python -m pytest $selection -q -p no:cacheprovider -m oracle";

  # The selected rules, the layout at width 120, and the future import in
  # every file. `ruff.toml` in the pyterm root says what each rule is for.
  ruff = suite {
    name = "ptkhx-ruff";
    inputs = [ ruff ];
    setup = prepare + ''
      cp -r ${testSources}/ptkhx .
    '';
  } ''
    export RUFF_CACHE_DIR="$TMPDIR/ruff"
    ruff check ptkhx tests
    ruff format --check ptkhx tests
    missing=$(grep -rL '^from __future__ import annotations' --include='*.py' --exclude-dir='.*' --exclude-dir='__pycache__' ptkhx tests || true)
    if [ -n "$missing" ]; then
      echo "files without the future import:"
      echo "$missing"
      exit 1
    fi
  '';
}
