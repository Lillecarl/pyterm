# The sources the umbrella owns, each one a directory.
#
# `default.nix` calls it and hands each directory to `callPackage`. Nothing
# is evaluated here: a source is a directory, and what to import from it is
# the caller's decision.
{
  inputs ? import ./inputs.nix,

  # A working copy to use in place of one of the names.
  overrides ? { },
}:
builtins.mapAttrs (_: import ./fetch.nix) (inputs // overrides)
