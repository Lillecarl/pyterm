# A flake is not how this collection is built. It is here so that somebody
# can install pymux with one command, and for nothing else.
#
# `default.nix` is the whole definition. The checks and the dev shell are not
# exposed here on purpose: they read the environment through `builtins.getEnv`
# for the knobs that narrow a run, and a flake evaluates purely and would see
# none of them. `nix build --file . checks.all` is how the tests are run.
#
# A flake also sees only what git tracks, and the contents of a submodule are
# not that, so even a package build has to ask for them by name:
#
#     nix build '.?submodules=1#pymux'
{
  inputs.nixpkgs.url = "github:nixos/nixpkgs/nixpkgs-unstable";
  outputs =
    inputs:
    let
      inherit (inputs.nixpkgs) lib;
      forEachSystem = lib.genAttrs lib.systems.flakeExposed;
    in
    {
      packages = forEachSystem (
        system:
        let
          pkgs = import inputs.nixpkgs { inherit system; };
          defaultNix = import ./. { inherit pkgs; };
        in
        {
          default = defaultNix.pymux;
          inherit (defaultNix)
            pymux
            ptterm
            pyte
            prompt-toolkit
            umbrella
            ;
        }
      );
    };
}
