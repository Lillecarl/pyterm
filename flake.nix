# Everything here must be reachable without a flake entrypoint, so this file
# holds nothing but calls into default.nix.
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
      checks = forEachSystem (
        system:
        let
          pkgs = import inputs.nixpkgs { inherit system; };
        in
        # The fuzz run is not a gate, so `nix flake check` leaves it alone.
        # Reach it as `checks.ptterm-fuzz` through default.nix.
        removeAttrs (import ./. { inherit pkgs; }).checks [ "ptterm-fuzz" ]
      );
      devShells = forEachSystem (
        system:
        let
          pkgs = import inputs.nixpkgs { inherit system; };
        in
        {
          default = (import ./. { inherit pkgs; }).shell;
        }
      );
    };
}
