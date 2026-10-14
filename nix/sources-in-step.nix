# Every source's copy of what the root holds for all of them is the
# root's: `pkgs/sync-sources` writes the copies, and this runs it with
# `--check`.
{
  lib,
  callPackage,
  sources,
  sync-sources,
}:
let
  inherit (callPackage (sources.pyte + "/nix/suite.nix") { }) suite;

  ours = [
    "ptterm"
    "ptyhost"
    "pymux"
    "pysmithay"
    "pyte"
    "pyterm-pytest"
    "txterm"
  ];
  # A path joined and not interpolated: "${path}" would copy the whole
  # source to the store.
  copies = lib.concatMapStringsSep "\n" (name: ''
    mkdir -p tree/${name}
    touch tree/${name}/flake.nix
    cp ${sources.${name} + "/pyproject.toml"} tree/${name}/pyproject.toml
    cp ${sources.${name} + "/.gitignore"} tree/${name}/.gitignore
  '') ours;
in
suite {
  name = "pyterm-sources-in-step";
  inputs = [ sync-sources ];
} ''
  ${copies}
  mkdir -p tree/nix/shared
  cp ${../ruff.toml} tree/ruff.toml
  cp ${./shared/gitignore} tree/nix/shared/gitignore
  sync-sources --check tree
''
