# A wrapper: every output is an attribute of `default.nix`. Work on pysmithay
# happens in pyterm, which this repository is exported from.
{
  inputs.pyterm.url = "github:Lillecarl/pyterm";

  outputs =
    inputs:
    let
      inherit (inputs.pyterm.inputs.nixpkgs) lib;
      # Smithay is a Linux compositor.
      systems = [
        "x86_64-linux"
        "aarch64-linux"
      ];
      perSystem = lib.genAttrs systems (system: import ./default.nix { inherit inputs system; });
      forAllSystems = f: lib.mapAttrs (_: f) perSystem;
    in
    {
      packages = forAllSystems (p: {
        inherit (p) default pysmithay;
      });
      devShells = forAllSystems (p: {
        default = p.shell;
      });
    };
}
