# A flake is not how this collection is built. It is here so that somebody
# can install pymux with one command, and configure it with home-manager,
# and for nothing else.
#
# Neither of those is defined here. Both are attributes of `default.nix`
# that this file passes through, so a person with no flake reaches the same
# things: `(import ./. { }).pymux`, and
# `imports = [ ./nix/home-manager.nix ]`. A flake output is a way to reach
# what `default.nix` holds, never the place a thing is written.
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

      # The home-manager module. One module for every system, so it is not
      # inside `forEachSystem`, and it holds a path rather than a package,
      # so it needs no nixpkgs of its own.
      #
      # The default of its `package` option builds pymux out of the source
      # this flake was evaluated from. A flake sees only what git tracks,
      # so that source needs the submodules asked for by name:
      #
      #     pyterm.url = "git+https://github.com/Lillecarl/pyterm?submodules=1";
      inherit (import ./. { }) homeManagerModules;
    };
}
