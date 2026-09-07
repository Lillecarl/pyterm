# The package this repository builds. The suite that judges it lives in
# `nix/checks.nix`, which declares its own inputs.
#
# Three dependencies, and one of them is a debt:
#
# - `textual` draws, and `rich` comes with it.
# - `ptyhost` runs the program on a pty.
# - `ptterm` holds the parser and the screen. That layer imports no toolkit
#   and it belongs in `pyte`; it is here because that is where it was
#   written. `tests/test_the_layers.py` names every module of it this
#   package touches, and that list is what the move has to carry.
#   Lillecarl/pymux#11.
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
      ptterm
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

  checks = callPackage ./nix/checks.nix { inherit package testSources; };
in
package
