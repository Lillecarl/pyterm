# Every source the collection builds, each one a directory.
#
# Seven are in this tree. Each `default.nix` picks its own files with
# `lib.fileset`, so a `result` or a cache beside them changes no store path.
#
# Two come from outside, pinned in `npins/sources.json`; `npins update`
# moves a pin. prompt-toolkit is one of them because every patch there has
# to be one upstream could take. A checkout at `./prompt-toolkit`, which
# git ignores, takes its place when it holds anything: that is how an edit
# there reaches the next build. A flake never sees it, because a flake copies
# only what git tracks, so a flake build always takes the pin.
let
  pins = import ../npins;
  checkout = ../prompt-toolkit;
  hasCheckout = builtins.pathExists checkout && builtins.readDir checkout != { };
in
{
  pyte = ../pyte;
  ptyhost = ../ptyhost;
  ptterm = ../ptterm;
  txterm = ../txterm;
  pymux = ../pymux;
  pysmithay = ../pysmithay;
  pyterm-pytest = ../pyterm-pytest;
  prompt-toolkit = if hasCheckout then checkout else pins.prompt-toolkit.outPath;
  pyproject-nix = pins.pyproject-nix.outPath;
}
