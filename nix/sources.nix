# Every source the collection builds, each one a directory.
#
# Nine are in this tree. Each `package.nix` picks its own files with
# `lib.fileset`, so a `result` or a cache beside them changes no store path.
#
# Two come from outside, pinned in `flake.lock`: prompt-toolkit, because every
# patch there has to be one upstream could take, and pyproject.nix.
# `nix/compat.nix` says how a checkout at ./prompt-toolkit replaces its pin.
inputs:
let
  # flake-compatish gives an overridden input as a string. A path is what
  # copies the checkout, or one file of it, into the store; a string naming
  # a directory in $HOME reaches a derivation as text the sandbox cannot read.
  asPath = dir: if builtins.substring 0 11 dir == "/nix/store/" then dir else /. + dir;
in
{
  pyte = ../pyte;
  ptyhost = ../ptyhost;
  ptterm = ../ptterm;
  txterm = ../txterm;
  pymux = ../pymux;
  pysmithay = ../pysmithay;
  pyterm-pytest = ../pyterm-pytest;
  deferimport = ../deferimport;
  ptkhx = ../ptkhx;
  prompt-toolkit = asPath inputs.prompt-toolkit.outPath;
  pyproject-nix = inputs.pyproject-nix.outPath;
}
