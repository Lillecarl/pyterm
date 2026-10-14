# A wrapper. `default.nix` is the whole definition, and every output here
# is an attribute of it, so a person with no flake reaches the same things:
# `(import ./. { }).pymux`, and `imports = [ ./nix/home-manager.nix ]`.
#
# This file owns the pins. `nix/compat.nix` reads the same `flake.lock` for
# `default.nix`, through flake-compatish, so there is one lock.
#
# The checks are not here on purpose: they read the environment through
# `builtins.getEnv` for the knobs that narrow a run, and a flake evaluates
# purely. `nix build --file . checks.all` runs them.
{
  inputs = {
    nixpkgs.url = "github:NixOS/nixpkgs/nixpkgs-unstable";
    flake-compatish.url = "github:Lillecarl/flake-compatish";
    # Our branch of upstream's repository: every patch there has to be one
    # upstream could take. An ignored checkout at ./prompt-toolkit takes its
    # place, `nix/compat.nix` says how.
    prompt-toolkit = {
      url = "github:Lillecarl/python-prompt-toolkit/render-performance";
      flake = false;
    };
    pyproject-nix = {
      url = "github:pyproject-nix/pyproject.nix";
      flake = false;
    };
  };

  outputs =
    inputs:
    let
      inherit (inputs.nixpkgs) lib;
      systems = [
        "x86_64-linux"
        "aarch64-linux"
        "aarch64-darwin"
      ];
      perSystem = lib.genAttrs systems (system: import ./default.nix { inherit inputs system; });
      forAllSystems = f: lib.mapAttrs (_: f) perSystem;
    in
    {
      packages = forAllSystems (p: {
        default = p.pymux;
        inherit (p)
          pymux
          libpymux
          ptterm
          pyte
          prompt-toolkit
          ;
      });
      devShells = forAllSystems (p: {
        default = p.shell;
      });

      # One module for every system: it holds a path, and builds pymux from
      # the consumer's own pkgs.
      homeManagerModules.default = ./nix/home-manager.nix;
    };
}
