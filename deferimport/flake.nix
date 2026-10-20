# A wrapper: every output is an attribute of `default.nix`. Work on deferimport
# happens in pyterm, which this repository is exported from.
{
  inputs.pyterm.url = "github:Lillecarl/pyterm";

  outputs =
    inputs:
    let
      inherit (inputs.pyterm.inputs.nixpkgs) lib;
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
        inherit (p) default deferimport;
      });
      devShells = forAllSystems (p: {
        default = p.shell;
      });
      # For a project outside pyterm: `python3.pkgs.deferimport` in any
      # nixpkgs. A file of its own, because it needs nothing of pyterm.
      overlays.default = import ./overlay.nix;
    };
}
