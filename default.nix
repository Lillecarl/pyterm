{
  pkgs ? import <nixpkgs> { },
}:
let
  # umbrella drives this collection: it keeps a submodule commit that no remote
  # has out of the pointers recorded here, and makes worktreespaces that share
  # storage instead of cloning every repository again.
  #
  # It is a submodule too, so it can be edited in place like the rest. It is
  # also the tool that checks the submodules out, so a clone made without them
  # has to be able to build it anyway: when the directory is not there, fall
  # back to the commit this repository pins.
  umbrellaSource =
    if builtins.pathExists ./umbrella/default.nix then
      ./umbrella
    else
      pkgs.fetchFromGitHub {
        owner = "Lillecarl";
        repo = "umbrella";
        rev = "2302d8d376a8ce415fe544416958ba24f05922f6";
        hash = "sha256-y/Yownj5+DRPWKo3fATxPxpacNsP0SvKwU0DH483OYE=";
      };
in
rec {
  umbrella = (import umbrellaSource { inherit pkgs; }).umbrella;

  # Each submodule carries its own package definition and takes its siblings
  # as arguments, so nothing in them points at anything here. Built alone they
  # would get their dependencies from nixpkgs. Assembled here they get each
  # other, which is the point of keeping them in one checkout.
  pyte = pkgs.python3Packages.callPackage ./pyte { };

  prompt-toolkit = pkgs.python3Packages.callPackage ./prompt-toolkit { };

  ptterm = pkgs.python3Packages.callPackage ./ptterm {
    inherit prompt-toolkit pyte;
  };

  pymux = pkgs.python3Packages.callPackage ./pymux {
    inherit prompt-toolkit ptterm;
  };

  # Each package carries the tests that judge it, behind passthru. This is
  # where they get names, so `nix build --file . checks.ptterm` works from here.
  checks = {
    pyte = pyte.checks.tests;
    ptterm = ptterm.checks.tests;
    # Not a gate: it finds deviations from kitty faster than they get fixed.
    ptterm-fuzz = ptterm.checks.fuzz;
    pymux = pymux.checks.pymux;
    pymux-pty = pymux.checks.pty;
    # Not a gate on its own: it judges the run against a recorded list
    # of the tests that fail today, and complains at a difference in
    # either direction.
    pymux-esctest = pymux.checks.esctest;
  };

  shell = pkgs.callPackage ./pkgs/shell {
    inherit
      prompt-toolkit
      pyte
      ptterm
      pymux
      umbrella
      ;
  };
}
