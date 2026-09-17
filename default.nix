{
  pkgs ? import <nixpkgs> { },
}:
let
  inherit (pkgs) lib;

  # The eight sources the umbrella owns, each one a directory.
  #
  # `nix/sources.nix` says where each comes from and `nix/sources.lock` says
  # which revision; `nix/resolve.nix` joins them. A working copy that holds
  # anything is read at the revision the lock names, so a build here and a
  # build in CI agree. UMBRELLA_DEV names the sources to read as plain
  # directories instead, and `.envrc` sets it to `all`: the loop here is to
  # edit a working copy and build without committing.
  #
  # So a clone with no working copies builds from the lock, and nothing has
  # to be checked out first.
  sources = import ./nix/wire.nix { };

  # The builders that assemble a virtualenv instead of a PYTHONPATH.
  # `nix/python-set.nix` says why, and why the third-party packages still
  # come from nixpkgs. Lillecarl/pymux#319.
  pyproject-nix = import sources.pyproject-nix { inherit (pkgs) lib; };
  ps = pkgs.callPackage ./nix/python-set.nix { inherit pyproject-nix; };

  # THE interpreter of the collection, and THE place its package scopes
  # are bent. pymux and every Python dependency of it build against
  # this one binding: the roots below resolve in its package scope,
  # every lifted package is checked against its ABI
  # (`nix/python-set.nix` throws on a mismatch), and the virtualenvs
  # are built from it.
  #
  # The bends ride `pythonPackagesExtensions`, not the interpreter's
  # own `packageOverrides`, because a check input of a raw nixpkgs
  # package resolves through the build-host splice of the scope, and
  # the splices keep the original flavors -- derivation arguments are
  # filtered out of an interpreter `.override`
  # (`pkgs/development/interpreters/python/cpython/default.nix:182`).
  # The extension list is composed into every scope of every
  # interpreter (`pkgs/development/interpreters/python/passthrufun.nix:91`),
  # so one bend holds for all of them at once.
  #
  # Each bend is scoped to 3.15 and no further: on the default python
  # this snapshot's packages are cached and tested, and bending them
  # would only cost a rebuild.
  pkgs' = pkgs.extend (_final: prev: {
    pythonPackagesExtensions = prev.pythonPackagesExtensions ++ [
      (pyFinal: pyPrev:
        lib.optionalAttrs (lib.versionAtLeast pyPrev.python.pythonVersion "3.15") {
          # The python315 of this snapshot is 3.15.0rc2, one release
          # candidate past the packages it brings, and the binary cache
          # holds no 3.15 build of them -- so the packages build from
          # source here, and their own suites run against the RC. What
          # follows is every package that would not build, brought to
          # the state upstream had reached for 3.15: a version bump
          # where one exists, and where none does, the smallest suite
          # bend that leaves the runtime untouched.

          # Nothing here draws into Tk -- the collection is a terminal
          # application -- and tkinter is the RC's own module, so there
          # is no version to bump: its Tk test suite fails wholesale.
          # matplotlib's default backend choice is the only thing that
          # reaches tkinter, so the Tk build is dropped from the
          # closure rather than carried untested.
          matplotlib = pyPrev.matplotlib.override { enableTk = false; };

          # Already the latest release (1.3.1). One test of a traceback
          # decoration does not survive the RC: a "did you mean"
          # suggestion renders differently. nixpkgs bends 3.14 breakage
          # the same way (`pkgs/development/python-modules/exceptiongroup/default.nix:47`);
          # this is the 3.15rc2 addition to it.
          exceptiongroup = pyPrev.exceptiongroup.overrideAttrs (old: {
            pytestFlagsArray = (old.pytestFlagsArray or [ ]) ++ [
              "--deselect"
              "tests/test_formatting.py::test_nameerror_suggestions_in_group"
            ];
          });

          # Bumped to the latest release, which tracks 3.15 final: the
          # snapshot's 3.2.0 misbehaves on the RC at runtime --
          # `date.today` reads the real clock where it travelled to
          # 1970 -- and the packages whose suites take time-machine as
          # a pytest plugin need the fixed behaviour. The suite of
          # 3.5.1 imports hypothesis, which is bumped below.
          time-machine = pyPrev.time-machine.overridePythonAttrs (old: rec {
            version = "3.5.1";
            src = pkgs.fetchFromGitHub {
              owner = "adamchainz";
              repo = "time-machine";
              tag = version;
              hash = "sha256-k/URZJz/kiPg20SYoOblaleIWdB8coaT/nHLAV7dDU0=";
            };
            # The suite grew the fuzz modules, and the module this
            # override re-enters never named hypothesis as a check
            # input -- 3.2.0's suite did not import it.
            nativeCheckInputs = (old.nativeCheckInputs or [ ])
              ++ [ pyFinal.hypothesis ];
            # The same tz-abbreviation quirk family the module already
            # disables for Africa/Addis_Ababa ("Assertion Errors
            # related to Africa/Addis_Ababa"): this tzdata spells
            # Nairobi's abbreviation `Africa` where the snapshots
            # expect `EAT`.
            disabledTests = (old.disabledTests or [ ]) ++ [
              "test_move_to_naive_string_uses_real_local_timezone"
              "test_move_to_naive_mode_local_uses_real_local_timezone"
              "test_move_to_unsupported_destination_keeps_timezone"
              "test_move_to_naive_mode_error_keeps_timezone"
              "test_naive_datetime_modes"
              "test_localtime_and_gmtime_match_datetime"
            ];
          });

          # Bumped: 0.20.0's suite builds a stable-ABI wheel to test
          # its tagging, and the RC refuses it; 0.21.1 is where
          # upstream tracks 3.15. numpy and everything above it take
          # this as their build system, so the cascade behind it is
          # large.
          meson-python = pyPrev.meson-python.overridePythonAttrs (_old: rec {
            version = "0.21.1";
            src = pkgs.fetchPypi {
              pname = "meson_python";
              inherit version;
              hash = "sha256-eLM0XcvA/te5Oefjep+qs1vdquB79i51QsitR5w5WvU=";
            };
          });

          # Bumped: the snapshot's 6.156.1 fails its own suite on the
          # RC, which removed `typing.ByteString` and its tests turn
          # the warning into an error. numpy names hypothesis among its
          # check inputs, so this gates numpy. The vendored rust tree
          # changed with the version, and the module pins that hash as
          # a literal, so the vendor fetch is recomputed here, in the
          # module's own shape, with the hash the failed staging
          # reported.
          hypothesis = pyPrev.hypothesis.overridePythonAttrs (old: rec {
            version = "6.168.0";
            src = pkgs.fetchFromGitHub {
              owner = "HypothesisWorks";
              repo = "hypothesis";
              tag = "v${version}";
              hash = "sha256-e2RM1TaPz/C1VovVstmZJ1CICE0v7OVhsrR08a6epP0=";
            };
            cargoDeps = pkgs.rustPlatform.fetchCargoVendor {
              inherit (old) pname;
              inherit version src;
              sourceRoot = "${src.name}/hypothesis";
              cargoRoot = "rust";
              hash = "sha256-6fvvOeaRDsoMoO6Jbk9jbl+xChSq1Vitsr5FqLzN8oI=";
            };
          });

          # Bumped: the snapshot's suite calls the private
          # `glob.glob1`, and the RC removed it. 4.65.0 is where
          # upstream moved off it.
          fonttools = pyPrev.fonttools.overridePythonAttrs (_old: rec {
            version = "4.65.0";
            src = pkgs.fetchFromGitHub {
              owner = "fonttools";
              repo = "fonttools";
              tag = version;
              hash = "sha256-6chZncheSuqoQdFk68fmNP46GNjhujOoM8IPQqqSspc=";
            };
          });

          # Already the latest release (15.0.0): two inspector tests
          # render differently on the RC, and there is no newer release
          # to take their snapshots from. The runtime the collection
          # uses is untouched, so only the two tests are skipped.
          rich = pyPrev.rich.overridePythonAttrs (old: {
            disabledTests = (old.disabledTests or [ ]) ++ [
              "test_inspect_builtin_function_except_python311"
              "test_inspect_builtin_function_only_python311"
              "test_inspect_integer_with_methods_python38_and_python39"
              "test_inspect_integer_with_methods_python310only"
              "test_inspect_integer_with_methods_python311"
              "test_attrs_broken"
            ];
          });

          # Already the latest release (0.22.1): one socket test of its
          # suite hits a bad file descriptor on the RC, in the C
          # extension the collection never reaches -- anyio tests the
          # uvloop backend, and the collection uses anyio's own loop.
          uvloop = pyPrev.uvloop.overridePythonAttrs (old: {
            disabledTests = (old.disabledTests or [ ]) ++ [
              "test_socket_sync_remove"
            ];
          });

          # Bumped: mypyc's compiled-run tests fail on the snapshot's
          # 2.1.0; 2.3.1 is where upstream tracks 3.15.
          mypy = pyPrev.mypy.overridePythonAttrs (_old: rec {
            version = "2.3.1";
            src = pkgs.fetchFromGitHub {
              owner = "python";
              repo = "mypy";
              tag = "v${version}";
              hash = "sha256-EkZVBWlT8l3oIC9UuDEJua6dxFDIL0o9k/3FJJFqMB4=";
            };
          });
        })
    ];
  });

  # The collection on one interpreter: the seven packages of the set,
  # the runnable venvs of the two front ends, and the dev environment.
  # Nothing here knows which python it is on -- the set is built for
  # the one interpreter it was handed, and the bends of the scopes
  # above pick themselves by version.
  mkScope =
    python:
    let
      set = ps.mkPythonSet {
        inherit python;

        # Nothing of ours is named here any more. The list is what the seven
        # `pyproject.toml` files ask for and nixpkgs supplies -- wcwidth,
        # pytest, textual, asyncssh and the rest -- read out of the
        # declarations rather than out of a build.
        nixpkgsRoots = ps.nixpkgsRootsFor {
          inherit python;
          projectRoots = [
            sources.pymux
            sources.txterm
            sources.ptterm
            sources.pyte
            sources.prompt-toolkit
            sources.ptyhost
            sources.pyterm-pytest
          ];
          # Everything this collection supplies for itself. A name left off
          # this list would not fail: nixpkgs would answer with its own
          # package, and the set would hold upstream's under our name.
          exclude = [
            "pymux"
            "ptterm"
            "prompt-toolkit"
            "pyterm-pytest"
            "pyte"
            "ptyhost"
            "txterm"
          ];
        };

        overlay = final: _prev: {
          # The test equipment the collection's suites share: the seats, the
          # drivers, the budgets. It takes the floor the widgets take and never
          # a layer above it, so every repository's checks can take it as an
          # input without a cycle. Lillecarl/pymux#274.
          pyterm-pytest = final.callPackage sources.pyterm-pytest {
            inherit (ps) mkProject;
          };

          # The toolkit under ptterm and pymux, and the one source here that is
          # somebody else's. It is packaged from this set like the rest, and its
          # own `pyproject.toml` is read exactly as upstream wrote it: a
          # build-system swap is not a patch upstream could take.
          #
          # The attribute is `prompt-toolkit` and the project is
          # `prompt_toolkit`. That is PEP 503 normalisation, and it is the
          # spelling every dependency of it resolves to.
          prompt-toolkit = final.callPackage sources.prompt-toolkit {
            inherit (ps) mkProject;
          };

          # The floor: the parser, the screen and everything under them. Both
          # widgets take it, and it takes nothing of theirs.
          pyte = final.callPackage sources.pyte {
            inherit (ps) mkProject;
          };

          # The layer that runs a program on a pty. It depends on nothing here,
          # which is the point: two widgets need it, and neither may drag a
          # toolkit in behind it. Lillecarl/pymux#85.
          ptyhost = final.callPackage sources.ptyhost {
            inherit (ps) mkProject;
          };

          # The one terminal widget that the other two repositories reach: pymux
          # arranges several of them, and txterm borrows the conformance suite
          # that this one builds. Both take it from the set, which is why it had
          # to convert first -- a lifted package keeps a package's files and not
          # the passthru those tools ride on.
          ptterm = final.callPackage sources.ptterm {
            inherit (ps) mkProject;
          };

          pymux = final.callPackage sources.pymux {
            inherit (ps) mkProject;
            # The one that draws, which its checks need for kitty.
            inherit (pkgs) mesa;
            # The readers of the clipboard fence.
            inherit (pkgs) wl-clipboard xclip;
          };

          # The second front end: the same screen, drawn with Textual. It
          # takes the pure layer from pyte and no prompt_toolkit comes with
          # it, which is what Lillecarl/pymux#82 asks for -- and the set is
          # what keeps that true now, because a virtualenv holds exactly what
          # was asked for and nothing propagates into it.
          txterm = final.callPackage sources.txterm {
            inherit (ps) mkProject;
          };
        };
      };
    in
    rec {
      # The libraries of the collection, on this interpreter. Nothing
      # runs ptterm or pyte: they are the floors the venvs import, and
      # what the outside reaches from them is the passthru -- the
      # checks, and the conformance suites that pymux and txterm
      # borrow.
      inherit (set) ptterm pyte prompt-toolkit ptyhost pyterm-pytest;

      # pymux, as a person runs it: a virtualenv holding the package,
      # everything it declares, and the themes of the pastel. The checks
      # ride along from the package inside, which is where they are
      # written.
      pymux = set.mkVirtualEnv "pymux" { pymux = [ "catppuccin" ]; } // {
        inherit (set.pymux) checks;
        inherit (set.pymux) meta;
      };

      # The same, for the Textual front end: the venv is what has a
      # runnable `bin/txterm`, and the checks ride along from the
      # package inside it.
      txterm = set.mkVirtualEnv "txterm" { txterm = [ ]; } // {
        inherit (set.txterm) checks;
        inherit (set.txterm) meta;
      };

      # The python of the dev shell: the same virtualenv the suites run
      # on, so what works by hand and what works in the sandbox are the
      # same thing.
      devEnv = set.mkVirtualEnv "pyterm-dev" {
        pymux = [
          "test"
          "dev"
          "catppuccin"
        ];
      };
    };
in
rec {
  inherit pkgs sources;

  # umbrella drives this collection. It is a source like the rest, so it can
  # be edited in place, and it is also the tool that fetches the others --
  # which the lock makes possible without it.
  umbrella = (import sources.umbrella { inherit pkgs; }).umbrella;

  # The collection's package scopes, one per interpreter: the same
  # seven sources and the same venvs, built on each python the
  # collection supports. The bends of the scopes live in the one place
  # above and pick themselves by version; this is where a build is
  # picked.
  scopes = {
    python3 = mkScope pkgs'.python3;
    python315 = mkScope pkgs'.python315;
  };

  # The interpreter the collection is on by default: the nixpkgs
  # default, whose packages the binary cache holds tested. Moving the
  # default is this line; the other scope stays built and reachable
  # either way -- `scopes.python315.pymux`, and so on.
  default = scopes.python3;

  pymux = default.pymux;

  txterm = default.txterm;

  ptterm = default.ptterm;

  pyte = default.pyte;

  prompt-toolkit = default.prompt-toolkit;

  ptyhost = default.ptyhost;

  pyterm-pytest = default.pyterm-pytest;

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
    # Seven are left out, and none of them is a gate. The profile and
    # the latency measurement both read a wall clock, which says
    # nothing twice in a sandbox beside other jobs; they are
    # instrumentation, and reading them is the work. The fuzz hunt
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
        "pymux-latency"
        "pymux-profile"
        "pymux-theme-pictures"
        "pymux-vttest-pictures"
        "pyte-roaming"
      ];
    };
  };

  # The site: the galleries of everything pymux draws, laid out for a
  # person to read in a browser. The picture checks are galleries
  # already -- runs whose output is a tree of pictures beside their
  # logs -- and this is the page around them: one section per check.
  # The GitHub Action deploys it, so the pictures are read without a
  # checkout of the collection.
  site = pkgs.callPackage ./nix/site.nix {
    sections = [
      {
        name = "panes";
        title = "A terminal, without and with pymux";
        text = "Every fixture photographed twice: the program bare in the terminal, and the same program in a pane. The difference between the two is what pymux adds, and the still checks are judged against the recorded counts of exactly these differences.";
        run = checks.pymux-pictures.run;
      }
      {
        name = "chrome";
        title = "The chrome";
        text = "What pymux draws around a pane: the status line, a pane's title bar, the command palette, the overlay pane, the clock. This check judges nothing; reading the pictures is the work.";
        run = checks.pymux-chrome-pictures.run;
      }
      {
        name = "themes";
        title = "The themes";
        text = "Every theme `set-option theme` takes, in six terminals: the three dark ones and the same three on a light background, with the demo application in the pane. A theme that left the chrome hardcoded would show here.";
        # The gallery builds in pieces, one derivation per terminal
        # and per batch of themes, and the page sees them gathered:
        # the pieces write disjoint trees, and a rerun of the site
        # rebuilds only the combos that failed.
        # Lillecarl/pymux#284.
        run = pkgs.symlinkJoin {
          name = "pymux-theme-pictures";
          paths = builtins.map (combo: combo.run) (
            builtins.attrValues pymux.checks.themePictureCombos
          );
        };
      }
      {
        name = "vttest";
        title = "vttest, in a pane";
        text = "The walker drives vttest through its screens with pymux in the chain. The screens that differ are recorded in tests/vttest-picture-differences.txt, each with the reason above it.";
        run = checks.pymux-vttest-pictures.run;
      }
    ];
  };

  # A suite is named `<package>-<what it covers>`, and `unit` is the one that
  # needs nothing but python.
  suites = {
    # The one check that belongs to the collection and to no package:
    # only the umbrella can see all seven copies of `nix/suite.nix` at
    # once. Lillecarl/pymux#367.
    pyterm-one-suite-nix = pkgs.callPackage ./nix/one-suite-nix.nix {
      inherit sources;
    };
    pyte-unit = pyte.checks.unit;
    # The property tests of pyte, off a fresh seed. Not a gate: the
    # gate pins the draw so that a green run means the same thing
    # twice, and this is the run that still finds something new.
    pyte-roaming = pyte.checks.roaming;
    # The colour specs, judged against the real Xlib. `pyte/xcms.py` is a
    # port of the colour management of Xlib, and only a comparison against
    # the original says whether the port is right.
    pyte-xcms = pyte.checks.xcms;
    # The character set tables, judged against xterm's own source. The
    # national replacement sets are published nowhere as data, so
    # `charsets.h` is the list and this is what says the copy is right.
    # Lillecarl/pymux#111.
    pyte-xterm-tables = pyte.checks.xterm-tables;
    # The pty layer, on its own. It runs real programs on real ptys,
    # and one of its tests holds it to importing nothing at all.
    ptyhost-unit = ptyhost.checks.unit;
    # The equipment the suites share: the seats, the drivers, the
    # budgets. Its own gate is the ceiling; the suites that use it are
    # the real judges.
    pyterm-pytest-unit = pyterm-pytest.checks.unit;
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
    # What one keystroke costs, counted rather than timed: the key
    # going out to the pane's pty, the answer parsed, and the
    # renderer's diff and escape sequences coming back. It is the
    # gateable half of `pymux-latency`, which measures the same path
    # on a clock and therefore judges nothing.
    pymux-keystroke = pymux.checks.keystroke;
    # What pymux still holds after a pane, a window or a client has
    # gone. A multiplexer runs for weeks, so a pane's worth of objects
    # kept on every `kill-pane` is a leak nobody sees until the machine
    # swaps. A weak reference to everything a round makes says exactly
    # what survived, and the object count says what grows without
    # dying.
    pymux-leaks = pymux.checks.leaks;
    # What a pane that animates costs when nobody is looking at it. It
    # runs the real programs -- cmatrix, tty-clock, nyancat, pipes --
    # because a writer in a loop does not write the way one of those
    # does, and the fault it caught only shows for a program that
    # writes a screenful at a steady rate. The unit is a fraction of
    # one core, so the ceiling is loose: it separates 100% from 12%,
    # and is not a budget to tune.
    pymux-busy = pymux.checks.busy;
    # Where the time of a frame goes, sampled with pyinstrument while a
    # real server draws for a real client. Not a gate and it judges
    # nothing: a sampling profiler reports wall clock, and this sandbox
    # runs beside other jobs. It is instrumentation, and reading it is
    # the work.
    pymux-profile = pymux.checks.profile;
    # That the profiler still runs, which is a gate even though what it
    # measures is not. The instrument broke and nothing said so, because
    # the only thing that would have run it was the thing that broke.
    # Lillecarl/pymux#360.
    pymux-profile-starts = pymux.checks.profileStarts;
    # What pymux costs a keystroke, against the same program on a bare
    # pty. Not a gate either, and for the same reason the profile is
    # not: a millisecond belongs to the machine that read it. It is
    # the third of the three numbers Lillecarl/pymux#8 asked for, and
    # the only one an instruction count cannot give.
    pymux-latency = pymux.checks.latency;
    # How many turns of the event loop one keystroke costs. The number
    # in between the other two: an instruction count sees work and no
    # waiting, a millisecond sees the waiting and belongs to one
    # machine, and a turn of the loop is decided by the code. It holds
    # the shortest keystroke of the run to a number, because a loaded
    # machine can only add turns and never take one away.
    pymux-turns = pymux.checks.turns;
    # TEMPORARY scratch measurement for Lillecarl/pymux#258. Remove it
    # with the script and the check it runs.
    pymux-wire = pymux.checks.wire;
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
    # Every theme, with the demo application in the pane: the whole
    # gallery in `$out`, for a person to read side by side. Not a gate
    # either. Lillecarl/pymux#194, Lillecarl/pymux#195.
    pymux-theme-pictures = pymux.checks.themePictures;
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

  devEnv = default.devEnv;

  shell = pkgs.callPackage ./pkgs/shell {
    inherit devEnv umbrella;
  };
}
