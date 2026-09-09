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

  # The layer that runs a program on a pty. It depends on nothing, which
  # is the point: two widgets need it, and neither may drag its toolkit
  # in behind it. Lillecarl/pymux#85.
  ptyhost = pkgs.python3Packages.callPackage ./ptyhost { };

  ptterm = pkgs.python3Packages.callPackage ./ptterm {
    inherit prompt-toolkit ptyhost pyte;
  };

  # The second front end: the same screen, drawn with Textual. It takes
  # the pure layer from ptterm and no prompt_toolkit comes with it, which
  # is what Lillecarl/pymux#82 asks for.
  txterm = pkgs.python3Packages.callPackage ./txterm {
    inherit pyte ptyhost;
    # Not a dependency of the package: its suite runs the conformance
    # suite of xterm, which is built once in ptterm.
    inherit ptterm;
  };

  pymux = pkgs.python3Packages.callPackage ./pymux {
    inherit prompt-toolkit ptterm;
    # The one that draws, which its checks need for kitty. In the python
    # package set `mesa` is a python binding that nixpkgs has marked
    # broken, so it has to come from here.
    inherit (pkgs) mesa;
  };

  # The home-manager module, so `~/.pymux.conf` is generated rather than
  # placed by hand. Lillecarl/pymux#190.
  #
  # It is a path and nothing else, so `imports = [ ... ]` takes it straight.
  # `flake.nix` passes this same attribute through, which is why the module
  # is defined here: a flake output is a way for somebody else to reach
  # what this file holds, never the place a thing is written.
  homeManagerModules.default = ./nix/home-manager.nix;

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
    # Six are left out, and none of them is a gate. The profile is
    # instrumentation: it samples a wall clock, which says nothing
    # twice in a sandbox beside other jobs. The fuzz hunt
    # finds deviations from kitty faster than they get fixed, so it
    # would fail this most days. The vttest walk draws screens for a
    # person to read and judges none of them. The pictures of vttest
    # judge a real terminal, and that part is not settled yet. The
    # pictures of pymux's chrome judge nothing at all yet, because
    # there is no recorded image to judge them against. The roaming
    # property tests draw a fresh example every run, which is the one
    # thing a gate may not do.
    all = pkgs.callPackage ./nix/tests.nix {
      suites = removeAttrs suites [
        "ptterm-fuzz"
        "ptterm-vttest"
        "pymux-chrome-pictures"
        "pymux-profile"
        "pymux-vttest-pictures"
        "pyte-roaming"
      ];
    };
  };

  # A suite is named `<package>-<what it covers>`, and `unit` is the one that
  # needs nothing but python.
  suites = {
    pyte-unit = pyte.checks.unit;
    # The property tests of pyte, off a fresh seed. Not a gate: the
    # gate pins the draw so that a green run means the same thing
    # twice, and this is the run that still finds something new.
    pyte-roaming = pyte.checks.roaming;
    # The colour specs, judged against the real Xlib. `pyte/xcms.py` is a
    # port of the colour management of Xlib, and only a comparison against
    # the original says whether the port is right.
    pyte-xcms = pyte.checks.xcms;
    # The pty layer, on its own. It runs real programs on real ptys,
    # and one of its tests holds it to importing nothing at all.
    ptyhost-unit = ptyhost.checks.unit;
    # The suite prompt-toolkit ships. ptterm and pymux are both built on
    # this fork, so a change to it that breaks the library breaks them,
    # and nothing here said so until this ran.
    prompt-toolkit-unit = prompt-toolkit.checks.unit;
    # Two, split by what they need. `ptterm-unit` needs nothing but
    # python, and it is seventeen of the thirty-six test files. The
    # tests that judge the screen rather than the widget moved to
    # `pyte-unit` and `pyte-xcms`. Lillecarl/pymux#11.
    ptterm-unit = ptterm.checks.unit;
    ptterm-panel = ptterm.checks.panel;
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
    # And what a scrollback costs to hold, rather than to touch. Bytes
    # are the same on every machine, so a budget file holds them.
    ptterm-footprint = ptterm.checks.footprint;
    # Not a gate: it finds deviations from kitty faster than they get fixed.
    ptterm-fuzz = ptterm.checks.fuzz;
    # Not a gate either. vttest draws a screen and asks a person whether
    # what they see is right, so this walks its menus and keeps every
    # screen. Reading them is the work. Lillecarl/pymux#46.
    ptterm-vttest = ptterm.checks.vttest;
    # The Textual widget: what it draws, read as the segments it
    # returns, and a real program on a pty under Textual's own driver.
    txterm-unit = txterm.checks.unit;
    # The conformance suite of xterm again, this time as a program in a
    # Textual widget. ptterm runs it on a bare pty with no toolkit, so
    # the two lists together say what a front end adds.
    txterm-esctest = txterm.checks.esctest;
    pymux-unit = pymux.checks.unit;
    # What it costs to lay a window out and draw the frame around its
    # panes, in bytecode instructions. The sibling of
    # `ptterm-instructions`, one layer up: that one measures what a
    # pane costs, and this one measures what arranging several of them
    # costs. It holds each count to a budget, so a change that makes a
    # frame much more expensive fails here instead of being felt later.
    pymux-frame = pymux.checks.frame;
    # What pymux still holds after a pane, a window or a client has
    # gone. A multiplexer runs for weeks, so a pane's worth of objects
    # kept on every `kill-pane` is a leak nobody sees until the machine
    # swaps. A weak reference to everything a round makes says exactly
    # what survived, and the object count says what grows without
    # dying.
    pymux-leaks = pymux.checks.leaks;
    # Where the time of a frame goes, sampled with pyinstrument while a
    # real server draws for a real client. Not a gate and it judges
    # nothing: a sampling profiler reports wall clock, and this sandbox
    # runs beside other jobs. It is instrumentation, and reading it is
    # the work.
    pymux-profile = pymux.checks.profile;
    pymux-pty = pymux.checks.pty;
    # The same end to end test, with the server and the client in one
    # process and no socket between them.
    pymux-integrated = pymux.checks.integrated;
    # A picture of a real terminal, with pymux in it and without it.
    # The result is a directory of pictures, so a run always leaves
    # something to look at.
    pymux-pictures = pymux.checks.pictures;
    # The same picture, of vttest. Not a gate: the chain is proven and
    # the judging is not, and it is minutes of work for one item of
    # vttest's main menu.
    pymux-vttest-pictures = pymux.checks.vttestPictures;
    # A picture of what pymux draws around a pane: the status line, a
    # title bar, the command palette, a strip. Not a gate either, and
    # it judges nothing: the chrome is the thing pymux adds, so there
    # is no bare side to subtract from. Reading the pictures is the
    # work. Lillecarl/pymux#161.
    pymux-chrome-pictures = pymux.checks.chromePictures;
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
    # The home-manager module, judged by pymux. Nix writes the
    # configuration file the module generates, and pymux reads it through
    # the same `source-file` a real startup runs. It is named for this
    # repository and not for pymux, because the module lives here.
    pyterm-home-manager = pkgs.callPackage ./nix/home-manager-check.nix {
      inherit pymux;
    };
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
