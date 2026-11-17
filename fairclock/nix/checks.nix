# The suites that judge fairclock.
#
# It declares its own inputs, so `default.nix` holds the package and carries
# nothing that only a test needs. `nix/suite.nix` says why a check is two
# derivations.
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
  #     FAIRCLOCK_TESTS=tests/test_fairclock.py nix build --file . checks.fairclock-unit
  selection = builtins.getEnv "FAIRCLOCK_TESTS";

  prepare = ''
    cp -r ${testSources}/tests .
    cp ${testSources}/pyproject.toml .
    chmod -R +w .
    export HOME="$TMPDIR"
    export LANG=C.UTF-8
  '';
in
{
  # Every front end, on an idle machine and on a crowded CPU.
  unit = suite {
    name = "fairclock-unit";
    inputs = [ testEnv ];
    env = { inherit selection; };
    setup = prepare;
  } "python -m pytest $selection -q -p no:cacheprovider";

  # The selected rules, the layout at width 120, and the future import in
  # every file. `ruff.toml` in the pyterm root says what each rule is for.
  ruff = suite {
    name = "fairclock-ruff";
    inputs = [ ruff ];
    setup = prepare + ''
      cp -r ${testSources}/fairclock .
    '';
  } ''
    export RUFF_CACHE_DIR="$TMPDIR/ruff"
    ruff check fairclock tests
    ruff format --check fairclock tests
    missing=$(grep -rL '^from __future__ import annotations' --include='*.py' --exclude-dir='.*' --exclude-dir='__pycache__' fairclock tests || true)
    if [ -n "$missing" ]; then
      echo "files without the future import:"
      echo "$missing"
      exit 1
    fi
  '';
}
