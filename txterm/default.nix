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
# **This is a pyproject.nix builders package, not a nixpkgs one.** The three
# dependencies are declared once, in `pyproject.toml`, and the renderer reads
# them; an environment is a virtualenv rather than a PYTHONPATH.
# Lillecarl/pymux#319.
#
# Nothing else belongs in this repository: the dev shell and the collection
# that assembles this with its siblings live in pyterm.
{
  lib,
  stdenv,
  python,
  pyprojectHook,
  resolveBuildSystem,
  mkVirtualEnv,
  mkProject,
  callPackage,
  ptterm,
}:
let
  # What the wheel is built from, and nothing else. A denylist would carry
  # `tests`, `examples` and the `.ruff_cache` a local run rewrites, and a
  # source that a test run changes rebuilds everything below it.
  # Lillecarl/pymux#320.
  projectRoot = lib.fileset.toSource {
    root = ./.;
    fileset = lib.fileset.unions [
      # Not only the `.py` files: `py.typed` is what tells a checker that
      # the annotations here are meant to be read. The filter is what
      # keeps `__pycache__` out, which a local run writes.
      (lib.fileset.fileFilter (file: file.hasExt "py" || file.name == "py.typed") ./txterm)
      ./pyproject.toml
      ./README.md
      ./LICENSE
    ];
  };

  package =
    (mkProject {
      inherit projectRoot python;
      extra = rendered: {
        passthru = rendered.passthru // { inherit checks; };

        meta = rendered.meta // {
          description = "A terminal widget for Textual";
          homepage = "https://github.com/Lillecarl/txterm";
          license = lib.licenses.bsd3;
          mainProgram = "txterm";
        };
      };
    })
      {
        inherit stdenv pyprojectHook resolveBuildSystem;
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

  # What the suites run on: txterm, everything it declares, and the `test`
  # extra beside them in the same file.
  testEnv = mkVirtualEnv "txterm-test-env" { txterm = [ "test" ]; };

  # The conformance suite of xterm is built once, in ptterm, and pymux
  # takes it from there as well. A tool is not a suite: what changes here
  # is which terminal it judges.
  #
  # This is the only reason `ptterm` is an argument at all. It is a build
  # input of a check and reaches the closure of nothing that runs, and it
  # comes from the set: ptterm is a builders package too, so the copy in
  # the scope is the one that carries the tools.
  checks = callPackage ./nix/checks.nix {
    inherit testEnv testSources;
    inherit (ptterm) esctest2;
  };
in
package
