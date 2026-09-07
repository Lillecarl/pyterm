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
  esctest2,
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

  # Which esctest2 tests run. A regular expression matched against the
  # name, for instance
  # `TXTERM_ESCTEST_INCLUDE=BSTests nix build --file . checks.txterm-esctest`.
  esctestInclude =
    let
      value = builtins.getEnv "TXTERM_ESCTEST_INCLUDE";
    in
    if value == "" then ".*" else value;

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

  # The conformance suite of xterm, running as a program inside a txterm
  # widget, inside a Textual application, on Textual's own event loop.
  #
  # ptterm runs the same suite on a bare pty with no toolkit anywhere.
  # **The two lists together are the proof that the screen layer is
  # shared**: a name that fails here and passes there is txterm's own.
  # Lillecarl/pymux#82.
  #
  # It is not a pass or fail of its own. The run is judged against
  # `tests/esctest-failures.txt`, and a difference either way fails.
  esctest = suite {
    name = "txterm-esctest";
    inputs = [
      pythonWithTests
      esctest2
    ];
    env = { inherit esctestInclude; };
    setup = prepare + ''
      export TXTERM_ESCTEST=${esctest2}/share/esctest2
      export TXTERM_ESCTEST_INCLUDE="$esctestInclude"
      export TXTERM_ESCTEST_OUT="$out"
    '';
  } "python tests/drive_with_esctest.py";
}
