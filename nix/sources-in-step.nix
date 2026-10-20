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
    "deferimport"
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
  # What `pkgs/sync-sources` writes in a source.
  copied = [
    "pyproject.toml"
    "README.md"
    ".gitignore"
    "default.nix"
    "shell.nix"
    "nix/compat.nix"
    ".github/workflows/pages.yml"
  ];
  copies = lib.concatMapStringsSep "\n" (name: ''
    mkdir -p tree/${name}/nix tree/${name}/.github/workflows
    touch tree/${name}/flake.nix
    ${lib.concatMapStringsSep "\n" (
      file: "cp ${sources.${name} + "/${file}"} tree/${name}/${file}"
    ) copied}
  '') ours;
in
suite {
  name = "pyterm-sources-in-step";
  inputs = [ sync-sources ];
} ''
  ${copies}
  mkdir -p tree/nix/shared
  cp ${../ruff.toml} tree/ruff.toml
  cp ${./shared}/* tree/nix/shared/
  sync-sources --check tree
''
