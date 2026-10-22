# Every source the collection builds, each one a directory.
#
# Nine are in this tree. Each `package.nix` picks its own files with
# `lib.fileset`, so a `result` or a cache beside them changes no store path.
#
# Two come from outside, pinned in `flake.lock`: prompt-toolkit, because every
# patch there has to be one upstream could take, and pyproject.nix.
# `nix/compat.nix` says how a checkout at ./prompt-toolkit replaces its pin.
inputs:
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
  # flake-compatish gives an overridden input's outPath as a path, which
  # copies the checkout into the store, and a pinned one as a store path.
  prompt-toolkit = inputs.prompt-toolkit.outPath;
  pyproject-nix = inputs.pyproject-nix.outPath;
}
