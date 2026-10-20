# The package this repository builds. The suite that judges it lives in
# `nix/checks.nix`, which declares its own inputs.
#
# **It takes nothing but the standard library**, because it runs before
# anything else is imported, and every source may take it as an input.
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
}:
let
  package =
    (mkProject {
      root = ./.;
      inherit python;
      extra = rendered: {
        passthru = rendered.passthru // { inherit checks; };

        meta = rendered.meta // {
          description = "Make plain imports lazy at import time, with no `lazy` keyword in the source";
          homepage = "https://github.com/Lillecarl/deferimport";
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
      ./deferimport
    ];
  };

  testEnv = mkVirtualEnv "deferimport-test-env" { deferimport = [ "test" ]; };

  checks = callPackage ./nix/checks.nix {
    inherit testEnv testSources ruff;
  };
in
package
