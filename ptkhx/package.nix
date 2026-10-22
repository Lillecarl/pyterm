# The package this repository builds. The suite that judges it lives in
# `nix/checks.nix`, which declares its own inputs.
#
# **The editor takes the standard library alone**, and prompt_toolkit is
# only for the layer that puts it on a Buffer.
{
  lib,
  stdenv,
  pyprojectHook,
  resolveBuildSystem,
  mkVirtualEnv,
  mkProject,
  python,
  callPackage,
  # The linter and formatter that the `ruff` check runs.
  ruff,
  # Real Helix, which the oracle check compares every keymap case with.
  helix,
}:
let
  package =
    (mkProject {
      root = ./.;
      inherit python;
      extra = rendered: {
        passthru = rendered.passthru // { inherit checks; };

        meta = rendered.meta // {
          description = "Helix's modal editing for a prompt_toolkit buffer";
          homepage = "https://github.com/Lillecarl/ptkhx";
          license = lib.licenses.bsd3;
        };
      };
    })
      {
        inherit stdenv pyprojectHook resolveBuildSystem;
      };

  # Only the tests, not the whole repository: a copy of everything makes
  # the test runs rebuild on every unrelated edit. `pyproject.toml` comes
  # with them, because pytest reads its settings from the root it finds.
  testSources = lib.fileset.toSource {
    root = ./.;
    fileset = lib.fileset.unions [
      ./tests
      ./pyproject.toml
      # The `ruff` check reads the package beside the tests.
      ./ptkhx
    ];
  };

  testEnv = mkVirtualEnv "ptkhx-test-env" { ptkhx = [ "test" ]; };

  checks = callPackage ./nix/checks.nix {
    inherit
      testEnv
      testSources
      ruff
      helix
      ;
  };
in
package
