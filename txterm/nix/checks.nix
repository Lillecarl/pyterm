# The suite that judges txterm.
#
# It declares its own inputs, so `default.nix` holds the package and carries
# nothing that only a test needs.
#
# `package` and `testSources` come from `default.nix`: the first because a
# suite runs against the installed package, the second because it knows where
# the repository root is and this file does not.
#
# `nix/suite.nix` says why a check is two derivations.
{
  python,
  pytest,
  anyio,
  callPackage,
  package,
  testSources,
}:
let
  inherit (callPackage ./suite.nix { }) suite;

  # anyio carries the pytest plugin that runs a coroutine test. Without it
  # pytest fails one with "async def functions are not natively supported",
  # so no async test in this repository runs at all. Textual's own test
  # driver is async, so that is every test that runs an app.
  pythonWithTests = python.withPackages (ps: [
    package
    pytest
    anyio
  ]);

  # Narrow a run to one file or one test while hunting:
  #
  #     TXTERM_TESTS=tests/test_drawing.py \
  #       nix build --file . checks.txterm-unit
  selection = builtins.getEnv "TXTERM_TESTS";

  prepare = ''
    cp -r ${testSources}/tests .
    cp ${testSources}/pyproject.toml .
    chmod -R +w .
    export HOME="$TMPDIR"
    export LANG=C.UTF-8
    export PYTHONDONTWRITEBYTECODE=1
    # Textual reads the size of the terminal it runs in. There is none
    # in a sandbox, so the headless driver of `run_test` uses this.
    export COLUMNS=80
    export LINES=24
  '';
in
{
  # Everything here needs python, a pty and Textual's headless driver.
  # There is no real terminal, and no picture of one: what txterm draws
  # is judged as segments, which is what `render_line` returns.
  unit = suite {
    name = "txterm-unit";
    inputs = [ pythonWithTests ];
    env = { inherit selection; };
    setup = prepare;
  } "python -m pytest $selection -q -p no:cacheprovider";
}
