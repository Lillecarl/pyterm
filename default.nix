{
  pkgs ? import <nixpkgs> { },
}:
let
  inherit (pkgs) lib;
  # Each package is built from its submodule working copy, so an edit builds
  # without a commit. cleanSource drops .git and .jj, which matters here: .jj
  # changes on every jj command and would give the source a new hash each time.
  sourceOf = lib.cleanSource;

  # umbrella drives this collection: it keeps a submodule commit that no
  # remote has out of the pointers recorded here, and makes worktreespaces
  # that share storage instead of cloning four repositories again.
  umbrellaSource = pkgs.fetchFromGitHub {
    owner = "Lillecarl";
    repo = "umbrella";
    rev = "2302d8d376a8ce415fe544416958ba24f05922f6";
    hash = "sha256-y/Yownj5+DRPWKo3fATxPxpacNsP0SvKwU0DH483OYE=";
  };
in
rec {
  umbrella = (import umbrellaSource { inherit pkgs; }).umbrella;

  pyte = pkgs.python3Packages.callPackage ./pkgs/pyte { src = sourceOf ./pyte; };

  prompt-toolkit = pkgs.python3Packages.callPackage ./pkgs/prompt-toolkit {
    src = sourceOf ./prompt-toolkit;
  };

  ptterm = pkgs.python3Packages.callPackage ./pkgs/ptterm {
    src = sourceOf ./ptterm;
    inherit prompt-toolkit pyte;
  };

  pymux = pkgs.python3Packages.callPackage ./pkgs/pymux {
    src = sourceOf ./pymux;
    inherit prompt-toolkit ptterm;
  };

  shell = pkgs.callPackage ./pkgs/shell { inherit pymux umbrella; };
}
