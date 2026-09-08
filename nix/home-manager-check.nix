# Does the home-manager module write a file that pymux accepts?
#
# Two halves. Nix evaluates `nix/home-manager.nix` against stub options and
# writes out what it generated. Python then hands that file to pymux's own
# `source-file`, which is the command a real startup runs, and reads the
# values back. `nix/home-manager-judge.py` is that half.
#
# **The stubs stand in for home-manager.** `home.packages` and
# `home.file` are all this module writes, so those two are all the module
# system needs to evaluate it. Taking home-manager as an input would make
# this collection need it to run its own tests, and what is judged here is
# the module's own logic: the lines it writes, and the quoting of them.
#
# So this does not prove that `home.file.<name>.text` is spelled the way
# home-manager spells it. Only an evaluation against home-manager itself
# says that, and that is a thing to do once by hand rather than a gate that
# drags a second module system into every run.
#
# It lives here and not in `pymux/nix/checks.nix` because the module lives
# here: a test lives with the code it judges. It needs pymux to judge with,
# which arrives as an argument.
{
  lib,
  callPackage,
  writeText,
  python3,
  pymux,
}:
let
  inherit (callPackage ../pymux/nix/suite.nix { }) suite;

  # Everything the module writes into. The module system needs a
  # declaration for each, and nothing more than a declaration.
  stubs =
    { ... }:
    {
      options.home.packages = lib.mkOption {
        type = lib.types.listOf lib.types.package;
        default = [ ];
      };

      options.home.file = lib.mkOption {
        default = { };
        type = lib.types.attrsOf (
          lib.types.submodule {
            options.text = lib.mkOption { type = lib.types.lines; };
          }
        );
      };
    };

  evaluate =
    asked:
    (lib.evalModules {
      # The module reads `pkgs` in one place only: the default of the
      # `package` option. The evaluation below names a package, so nothing
      # forces that default and a stub is enough. Taking the real `pkgs`
      # here would break the rule that a package names its own inputs.
      specialArgs.pkgs = { };
      modules = [
        ./home-manager.nix
        stubs
        asked
      ];
    }).config;

  # What a person would write. `status-left` is the value that carries the
  # quoting: it holds a "#", a ":" and a trailing space, and pymux reads a
  # line with `shlex.split`.
  #
  # `package` is named rather than left to its default. The default builds
  # pymux out of this checkout, and forcing it here would evaluate the
  # collection a second time from inside one of its own checks.
  written = evaluate {
    programs.pymux = {
      enable = true;
      package = pymux;
      settings = {
        base-index = 1;
        history-limit = 5000;
        mouse = true;
        mode-keys = "vi";
        default-terminal = "xterm-256color";
        status-left = "[#h:#S] ";
        # A setting of null writes no line. `bell` is a real option, so a
        # line for it would be accepted and the judge would not see it;
        # the grep below is what sees it.
        bell = null;
      };
      extraConfig = ''
        bind-key "|" split-window -h
      '';
    };
  };

  conf = writeText "pymux.conf" written.home.file.".pymux.conf".text;

  # The module installs what it was given, and the option holds a package
  # rather than a string.
  installs = written.home.packages == [ pymux ];

  # pymux is importable from this, and so is everything it carries.
  #
  # `toPythonModule` is what makes it importable. pymux is built as an
  # application, so an environment holds its `bin` and leaves its modules
  # off the path, and the judge imports the modules.
  python = python3.withPackages (ps: [ (ps.toPythonModule pymux) ]);
in
suite { name = "pyterm-home-manager"; } ''
  cp ${conf} pymux.conf
  echo "the module wrote:"
  cat pymux.conf
  echo ""

  ${lib.optionalString (!installs) ''
    echo "the module did not install the package it was given" >&2
    exit 1
  ''}

  if grep -q '^set-option bell' pymux.conf; then
    echo "a setting of null still wrote a line" >&2
    exit 1
  fi

  ${python}/bin/python ${./home-manager-judge.py} pymux.conf
''
