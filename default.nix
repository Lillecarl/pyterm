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
    # The one that draws, which its checks need for kitty. In the python
    # package set `mesa` is a python binding that nixpkgs has marked
    # broken, so it has to come from here.
    inherit (pkgs) mesa;
  };

  # Each package carries the tests that judge it, behind passthru. This is
  # where they get names, so `nix build --file . checks.ptterm-unit` works from
  # here.
  #
  # A check is the verdict on a suite, and `checks.<name>.run` is the run it
  # judges: the log, and everything the suite left behind. `pyte/nix/suite.nix`
  # says why the two are separate.
  checks = suites // {
    # Every suite that is a gate, at once. `checks.all.run` is the report:
    # each one's output linked by name, and a summary of how each ended.
    #
    # The fuzz hunt is left out. It is not a gate: it finds deviations from
    # kitty faster than they get fixed, so it would fail this most days.
    all = pkgs.callPackage ./nix/tests.nix {
      suites = removeAttrs suites [ "ptterm-fuzz" ];
    };
  };

  # A suite is named `<package>-<what it covers>`, and `unit` is the one that
  # needs nothing but python.
  suites = {
    pyte-unit = pyte.checks.unit;
    # The suite prompt-toolkit ships. ptterm and pymux are both built on
    # this fork, so a change to it that breaks the library breaks them,
    # and nothing here said so until this ran.
    prompt-toolkit-unit = prompt-toolkit.checks.unit;
    # Three, split by what they need. `ptterm-unit` needs nothing but
    # python, and it is about forty of the sixty test files.
    ptterm-unit = ptterm.checks.unit;
    ptterm-panel = ptterm.checks.panel;
    ptterm-xcms = ptterm.checks.xcms;
    # The conformance suite of xterm, on a pty of its own. It judges the
    # run against a recorded list of the tests that fail today, and
    # complains at a difference in either direction.
    ptterm-esctest = ptterm.checks.esctest;
    # The test suite of libvterm, driven by libvterm's own runner. It
    # judges the same list way: what fails today is written down, and a
    # difference in either direction fails.
    ptterm-vterm = ptterm.checks.vterm;
    # What it costs to parse a recording, in bytecode instructions and not in
    # seconds. It holds each count to a budget, so a change that makes the
    # parser much slower fails here instead of being felt later.
    ptterm-instructions = ptterm.checks.instructions;
    # Not a gate: it finds deviations from kitty faster than they get fixed.
    ptterm-fuzz = ptterm.checks.fuzz;
    pymux-unit = pymux.checks.unit;
    pymux-pty = pymux.checks.pty;
    # The same end to end test, with the server and the client in one
    # process and no socket between them.
    pymux-integrated = pymux.checks.integrated;
    # A picture of a real terminal, with pymux in it and without it.
    # The result is a directory of pictures, so a run always leaves
    # something to look at.
    pymux-pictures = pymux.checks.pictures;
    # Not a gate on its own: it judges the run against a recorded list
    # of the tests that fail today, and complains at a difference in
    # either direction.
    pymux-esctest = pymux.checks.esctest;
    # The test suite of libvterm, with pymux in the middle. A real
    # libvterm reads what pymux emitted and answers the assertions, so
    # this judges the wire and not the model.
    pymux-vterm = pymux.checks.vterm;
    # The reference tests of Alacritty, the same way. It is the slowest
    # gate here: a pane of its own for each of the 40, and one of the
    # recordings is a third of a megabyte.
    pymux-alacritty = pymux.checks.alacritty;
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
