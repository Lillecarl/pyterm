# A nixpkgs overlay that puts deferimport in every Python package set:
#
#     pkgs = import <nixpkgs> { overlays = [ (import ./overlay.nix) ]; };
#     pkgs.python3.withPackages (p: [ p.deferimport ])
#
# It needs nothing of pyterm. The flake passes it through as
# `overlays.default`.
_final: prev: {
  pythonPackagesExtensions = prev.pythonPackagesExtensions ++ [ (import ./nix/python-overlay.nix) ];
}
