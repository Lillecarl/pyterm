# The suite that judges txterm.
#
# It declares its own inputs, so `default.nix` holds the package and carries
# nothing that only a test needs.
#
# `testEnv` and `testSources` come from `default.nix`: the first because a
# suite runs against the installed package, the second because it knows where
# the repository root is and this file does not.
#
# `nix/suite.nix` says why a check is two derivations.
{
  # The python every suite runs on: a virtualenv of txterm, what txterm
  # declares, and its `test` extra. `default.nix` builds it from
  # `pyproject.toml`, so what a suite may import is what the package
  # declares and there is no second list here. Lillecarl/pymux#319.
  testEnv,
  callPackage,
  testSources,
  esctest2,
  # The linter and formatter that the `ruff` check runs.
  ruff,
}:
let
  inherit (callPackage ./suite.nix { }) suite;

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
    inputs = [ testEnv ];
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
      testEnv
      esctest2
    ];
    env = { inherit esctestInclude; };
    setup = prepare + ''
      export TXTERM_ESCTEST=${esctest2}/share/esctest2
      export TXTERM_ESCTEST_INCLUDE="$esctestInclude"
      export TXTERM_ESCTEST_OUT="$out"
    '';
  } "python tests/drive_with_esctest.py";

  # The style of txterm, held by the linter and the formatter rather
  # than by a run.
  #
  # `ruff check` holds the selected rules and `ruff format --check`
  # holds the layout at width 120, both read from the `pyproject.toml`
  # beside them. Neither can see the one thing the lazy annotations
  # rest on -- the presence of `from __future__ import annotations`
  # in every file -- so a grep holds that: UP037 unquotes only where
  # the import made the annotation lazy, and stays silent without it.
  # `ruff.toml` beside the umbrella says what each rule is for.
  #
  # The package stays out of the shared `prepare`: a `txterm/` beside
  # the tests shadows the installed package, and the suites above
  # judge the artifact, not the tree. The `ruff` check never imports.
  ruff = suite {
    name = "txterm-ruff";
    inputs = [ ruff ];
    setup = prepare + ''
      cp -r ${testSources}/txterm ${testSources}/examples .
    '';
  } ''
    export RUFF_CACHE_DIR="$TMPDIR/ruff"
    ruff check txterm tests examples
    ruff format --check txterm tests examples
    missing=$(grep -rL '^from __future__ import annotations' --include='*.py' --exclude-dir='.*' --exclude-dir='__pycache__' txterm tests examples || true)
    if [ -n "$missing" ]; then
      echo "files without the future import:"
      echo "$missing"
      exit 1
    fi
  '';
}
