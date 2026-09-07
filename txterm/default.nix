# The package this repository builds. The suite that judges it lives in
# `nix/checks.nix`, which declares its own inputs.
#
# Three dependencies, and prompt-toolkit is not in the closure of any of them:
#
# - `textual` draws, and `rich` comes with it.
# - `ptyhost` runs the program on a pty.
# - `pyte` parses and holds the screen.
#
# The third one was `ptterm` until the pure layer moved. That made the
# prompt_toolkit widget a build dependency of the Textual one, and only a test
# kept the toolkit out of the code. Lillecarl/pymux#11.
#
# Nothing else belongs in this repository: the dev shell and the collection
# that assembles this with its siblings live in pyterm.
{
  lib,
  buildPythonPackage,
  setuptools,
  callPackage,
  textual,
  ptyhost,
  pyte,
  ptterm,
}:
let
  package = buildPythonPackage {
    pname = "txterm";
    version = "0.1";
    src = lib.cleanSource ./.;
    pyproject = true;

    # Only ruff and pytest configuration live in pyproject.toml, so the build
    # backend has to be named here rather than read from it.
    build-system = [ setuptools ];
    dependencies = [
      textual
      ptyhost
      pyte
    ];

    # The suite runs as `checks.unit`, against the installed package.
    doCheck = false;
    pythonImportsCheck = [ "txterm" ];

    passthru = { inherit checks; };

    meta = {
      description = "A terminal widget for Textual";
      homepage = "https://github.com/Lillecarl/txterm";
      license = lib.licenses.bsd3;
      mainProgram = "txterm";
    };
  };

  # Only the tests, not the whole repository. A copy of everything makes the
  # test runs rebuild on every unrelated edit.
  #
  # `pyproject.toml` comes with them: pytest reads its settings from the root
  # it finds, and a root with no config file is a root with no settings.
  testSources = lib.fileset.toSource {
    root = ./.;
    fileset = lib.fileset.unions [
      ./tests
      ./pyproject.toml
    ];
  };

  # The conformance suite of xterm is built once, in ptterm, and pymux
  # takes it from there as well. A tool is not a suite: what changes here
  # is which terminal it judges.
  #
  # This is the only reason `ptterm` is an argument at all. It is a build
  # input of a check and reaches the closure of nothing that runs.
  checks = callPackage ./nix/checks.nix {
    inherit package testSources;
    inherit (ptterm) esctest2;
  };
in
package
