let
  compat = import ./nix/compat.nix;
in
{
  inputs ? compat.inputs,
  system ? builtins.currentSystem,
  # Unfree for claude-code, which a scenario check drives. Overlays empty,
  # and config set, so nixpkgs never reads ~/.config/nixpkgs.
  pkgs ? import inputs.nixpkgs {
    inherit system;
    config.allowUnfree = true;
    overlays = [ ];
  },
  # A source to build from another directory: a clone of one source passes
  # itself here, so it builds against its siblings in this tree.
  sourceOverrides ? { },
}:
let
  inherit (pkgs) lib;

  # Every source, each one a directory. `nix/sources.nix` says where each
  # comes from.
  sources = import ./nix/sources.nix inputs // sourceOverrides;

  # The builders that assemble a virtualenv instead of a PYTHONPATH.
  # `nix/python-set.nix` says why, and why the third-party packages still
  # come from nixpkgs. Lillecarl/pymux#319.
  pyproject-nix = import sources.pyproject-nix { inherit (pkgs) lib; };
  ps = pkgs.callPackage ./nix/python-set.nix { inherit pyproject-nix; };

  # The mock model API the agent CLIs are driven against, so a scroll or a
  # repaint can be reproduced without a provider and without a token.
  # `nix/agents/README.md` is how each agent is aimed at it, and
  # `nix/agents/fixtures` is what it answers. pymux's scenario check drives
  # claude-code against it.
  #
  # It is a third-party tool nixpkgs does not hold, and node is in the build
  # closure for it alone: nothing the collection ships reaches it.
  aimock = pkgs.callPackage ./pkgs/aimock { nodejs = pkgs.nodejs_22; };

  # The collection builds on two interpreters, and only the 3.15
  # one is bent: its packages build from source against 3.15.0
  # final where the cache holds no build of them, while the
  # default python stays exactly as nixpkgs tested it. The bends
  # themselves live in `nix/python-bends.nix`, composed here into
  # the interpreter's own package scope.
  pkgs' = pkgs.extend (final: prev: {
    python315 = prev.python315.override (old: {
      packageOverrides = lib.composeExtensions (old.packageOverrides or (_: _: { }))
        (pkgs.callPackage ./nix/python-bends.nix { });
    });
  });

  /**
    Every `pyproject.toml` project this collection builds, as the
    directories that hold them.

    Seven are a source each. The eighth is libpymux,
    which is a project inside the repository of pymux: a caller that
    only drives a server takes that one and none of the rest.

    `nixpkgsRootsFor` reads the dependency declarations out of these,
    so a set that holds our packages knows what they ask nixpkgs for.
  */
  projectRoots = [
    sources.pymux
    (sources.pymux + "/libpymux")
    sources.txterm
    sources.ptterm
    sources.pyte
    sources.prompt-toolkit
    sources.ptyhost
    sources.pyterm-pytest
    sources.pysmithay
    sources.deferimport
  ];

  /**
    Everything this collection supplies for itself.

    A name left off this list would not fail: nixpkgs has a `pyte` and
    a `prompt-toolkit` of its own, so the lookup would succeed and the
    set would hold upstream's package under our name.

    maturin is here too. It is pysmithay's build system, and nixpkgs
    ships it as a program and not in a Python scope, so the package runs
    that program. A set outside this repository excludes this list, so
    the name has to be on it and not beside it.
  */
  suppliedNames = [
    "pymux"
    "libpymux"
    "ptterm"
    "prompt-toolkit"
    "prompt-toolkit-rs"
    "pymux-rs"
    "pysmithay"
    "pyterm-pytest"
    "pyte"
    "pyte-rs"
    "ptyhost"
    "txterm"
    "deferimport"
    "maturin"
  ];

  /**
    The nixpkgs packages this collection needs, on one interpreter.

    Nothing of ours is in it. The list is what the `pyproject.toml`
    files ask for and nixpkgs supplies -- wcwidth, pytest, textual,
    asyncssh and the rest -- read out of the declarations rather than
    out of a build.

    # Inputs

    `python`
    : The interpreter whose package scope the names resolve in
  */
  nixpkgsRootsOn = python: ps.nixpkgsRootsFor {
    inherit python projectRoots;
    exclude = suppliedNames;
  };

  /**
    This collection's own packages, as an overlay of a pyproject.nix
    builders set.

    A set outside this repository takes it the same way `mkScope` does:
    compose it into `mkPythonSet`'s `overlay`, with `nixpkgsRootsOn` in
    front of it so that everything these declare is there to resolve.

    Nothing in it knows which interpreter it is on. The set is built
    for the one it was handed.
  */
  overlay = final: _prev: {
    # The test equipment the collection's suites share: the seats, the
    # drivers, the budgets. It takes the floor the widgets take and never
    # a layer above it, so every repository's checks can take it as an
    # input without a cycle. Lillecarl/pymux#274.
    pyterm-pytest = final.callPackage (sources.pyterm-pytest + "/package.nix") {
      inherit (ps) mkProject;
      # The linter and formatter that `pyterm-pytest-ruff` runs.
      inherit (pkgs) ruff;
    };

    # Plain imports made lazy at import time. The standard library alone,
    # so any source may take it.
    deferimport = final.callPackage (sources.deferimport + "/package.nix") {
      inherit (ps) mkProject;
      inherit (pkgs) ruff;
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
    pyte = final.callPackage (sources.pyte + "/package.nix") {
      inherit (ps) mkProject;
      # The linter and formatter that `pyte-ruff` runs.
      inherit (pkgs) ruff;
    };

    # pyte's per-cell loops in Rust, which an embedder installs over the
    # Python ones. A project inside pyte's repository, the way libpymux is
    # inside pymux's. Lillecarl/pymux#566.
    pyte-rs = final.callPackage (sources.pyte + "/pyte_rs") {
      inherit (pkgs)
        rustPlatform
        cargo
        rustc
        maturin
        clippy
        rustfmt
        ;
    };

    # The layer that runs a program on a pty. It depends on nothing here,
    # which is the point: two widgets need it, and neither may drag a
    # toolkit in behind it. Lillecarl/pymux#85.
    ptyhost = final.callPackage (sources.ptyhost + "/package.nix") {
      inherit (ps) mkProject;
      # The linter and formatter that `ptyhost-ruff` runs, and the player
      # whose own reader judges an exported asciicast.
      inherit (pkgs) ruff asciinema;
    };

    # The one terminal widget that the other two repositories reach: pymux
    # arranges several of them, and txterm borrows the conformance suite
    # that this one builds. Both take it from the set, which is why it had
    # to convert first -- a lifted package keeps a package's files and not
    # the passthru those tools ride on.
    ptterm = final.callPackage (sources.ptterm + "/package.nix") {
      inherit (ps) mkProject;
      # The linter and formatter that `ptterm-ruff` runs.
      inherit (pkgs) ruff;
    };

    # prompt_toolkit's per-cell loops in Rust, which pymux installs over
    # the Python ones. A project inside pymux's repository, because
    # prompt-toolkit takes only patches upstream could take.
    # Lillecarl/pymux#566.
    prompt-toolkit-rs = final.callPackage (sources.pymux + "/prompt_toolkit_rs") {
      inherit (pkgs)
        rustPlatform
        cargo
        rustc
        maturin
        clippy
        rustfmt
        ;
    };

    # pymux's image loops in Rust, which pymux installs over its own
    # Python. It imports nothing of pymux, which depends on it.
    # Lillecarl/pymux#574.
    pymux-rs = final.callPackage (sources.pymux + "/pymux_rs") {
      inherit (pkgs)
        rustPlatform
        cargo
        rustc
        maturin
        clippy
        rustfmt
        ;
    };

    # A headless Wayland compositor on Smithay, which hands each window's
    # pixels to Python. Its own source, because nothing of pymux is in it.
    pysmithay = final.callPackage (sources.pysmithay + "/package.nix") {
      inherit (pkgs)
        rustPlatform
        cargo
        rustc
        maturin
        clippy
        rustfmt
        libxkbcommon
        pixman
        foot
        wl-clipboard
        dejavu_fonts
        makeFontsConf
        # The linter and formatter that `pysmithay-ruff` runs.
        ruff
        ;
    };

    # The client library, and the smallest thing here anybody imports:
    # a socket, a JSON message and platformdirs. It is what a program
    # that drives a server takes, in place of pymux and the toolkit
    # behind it. pymux takes it too -- the room a server binds in is
    # what both sides have to agree about.
    libpymux = final.callPackage (sources.pymux + "/libpymux") {
      inherit (ps) mkProject;
    };

    pymux = final.callPackage (sources.pymux + "/package.nix") {
      inherit (ps) mkProject;
      # The one that draws, which its checks need for kitty.
      inherit (pkgs) mesa;
      # The readers of the clipboard fence.
      inherit (pkgs) wl-clipboard xclip;
      # The static checker that `pymux-types` runs.
      inherit (pkgs) pyrefly;
      # The linter and formatter that `pymux-ruff` runs.
      inherit (pkgs) ruff;
      # The model API that the scenario check aims claude-code at.
      inherit aimock;
      # The PipeWire of `audio-server private`, in the closure on Linux.
      # Pass null for either to leave it out. Lillecarl/pymux#657.
      pipewire = if pkgs.stdenv.hostPlatform.isLinux then pkgs.pipewire else null;
      wireplumber = if pkgs.stdenv.hostPlatform.isLinux then pkgs.wireplumber else null;
    };

    # The second front end: the same screen, drawn with Textual. It
    # takes the pure layer from pyte and no prompt_toolkit comes with
    # it, which is what Lillecarl/pymux#82 asks for -- and the set is
    # what keeps that true now, because a virtualenv holds exactly what
    # was asked for and nothing propagates into it.
    txterm = final.callPackage (sources.txterm + "/package.nix") {
      inherit (ps) mkProject;
      # The linter and formatter that `txterm-ruff` runs.
      inherit (pkgs) ruff;
    };
  };

  # The collection on one interpreter: the eight packages of the set,
  # the runnable venvs of the two front ends, and the dev environment.
  # Nothing here knows which python it is on -- the set is built for
  # the one interpreter it was handed, and the bends of the scopes
  # above pick themselves by version.
  mkScope =
    python:
    let
      set = ps.mkPythonSet {
        inherit python overlay;
        nixpkgsRoots = nixpkgsRootsOn python;
      };
    in
    rec {
      # The libraries of the collection, on this interpreter. Nothing
      # runs ptterm or pyte: they are the floors the venvs import, and
      # what the outside reaches from them is the passthru -- the
      # checks, and the conformance suites that pymux and txterm
      # borrow.
      inherit (set)
        ptterm
        pyte
        pyte-rs
        prompt-toolkit
        prompt-toolkit-rs
        pymux-rs
        pysmithay
        ptyhost
        pyterm-pytest
        libpymux
        deferimport
        ;

      # pymux, as a person runs it: a virtualenv holding the package,
      # everything it declares, the themes of the pastel, and on Linux
      # the compositor for panes with no display (`wayland-server`). The
      # checks ride along from the package inside, which is where they
      # are written.
      pymux = set.mkVirtualEnv "pymux" { pymux = [ "catppuccin" "wayland" ]; } // {
        inherit (set.pymux) checks;
        inherit (set.pymux) meta;
        # `<pymux-pane>` compiled, which is a thing to reach on its own:
        # a front end built with node links it and never the venv.
        inherit (set.pymux) element;
      };

      # pymux with `pymux web`, which serves a pane to a browser.
      #
      # **A second attribute and not an extra on the one above**, because
      # somebody installing a terminal multiplexer should not get a web
      # server they did not ask for. The cost is small -- `websockets` is
      # pure python and the front end is five files -- and the reason is
      # not the closure: a port that shows a terminal is a thing to choose
      # rather than to find. Lillecarl/pymux#461.
      pymux-web = set.mkVirtualEnv "pymux-web" {
        pymux = [
          "catppuccin"
          "web"
        ];
      };

      # The same, for the Textual front end: the venv is what has a
      # runnable `bin/txterm`, and the checks ride along from the
      # package inside it.
      txterm = set.mkVirtualEnv "txterm" { txterm = [ ]; } // {
        inherit (set.txterm) checks;
        inherit (set.txterm) meta;
      };

      # A source's package with every extra it declares, `docs` among
      # them, which its site is built in: autodoc imports what it
      # documents, optional modules too.
      docsEnv =
        name:
        set.mkVirtualEnv "${name}-docs" {
          ${name} = lib.attrNames
            (lib.importTOML (sources.${name} + "/pyproject.toml")).project.optional-dependencies;
        };

      # The python of the dev shell: the same virtualenv the suites run
      # on, so what works by hand and what works in the sandbox are the
      # same thing.
      devEnv = set.mkVirtualEnv "pyterm-dev" {
        pymux = [
          "test"
          "dev"
          "catppuccin"
          # So that `pymux web` runs by hand in the shell, and the suite
          # that judges it has the library in the sandbox.
          "web"
        ];
      };
    };
in
rec {
  inherit pkgs sources aimock;

  # Writes each source's flake.lock from this one, and checks them before an
  # export. Lillecarl/pymux#670.
  lock-subtrees = pkgs.callPackage ./pkgs/lock-subtrees { };
  # Filters each source out of this repository into its own. Lillecarl/pymux#667.
  josh-export = pkgs.callPackage ./pkgs/josh-export { };
  # Copies what the root holds for every source into each one, and
  # `checks.pyterm-sources-in-step` holds the copies.
  sync-sources = pkgs.callPackage ./pkgs/sync-sources { };


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

  # The builders of the set, for somebody assembling one of their own.
  # `nix/python-set.nix` says what each does. A caller that wants this
  # collection inside their own python set needs these three, the
  # `overlay` below and a `pkgs` of their own: nothing here imports
  # nixpkgs, so the one passed in is the one everything builds against.
  inherit (ps) mkPythonSet nixpkgsRootsFor mkProject;

  inherit
    overlay
    nixpkgsRootsOn
    projectRoots
    suppliedNames
    ;

  pymux = default.pymux;

  # pymux with `pymux web`. See the comment beside it: the web parts are a
  # thing to choose, not the default.
  pymux-web = default.pymux-web;

  # `<pymux-pane>` on its own: the compiled element, its declarations and a
  # `package.json`, so a front end built with node links `$out` as
  # `node_modules/pymux-pane` and imports it by name.
  #
  # **A separate output and not a path inside the venv.** The same files are
  # in `lib/python3.x/site-packages/pymux/web/static/`, and that path
  # carries the interpreter's version in it: a consumer reaching in there
  # breaks when the collection moves interpreter. This one does not move.
  # `checks.pymux-element` judges the declarations it publishes.
  # Lillecarl/pymux#461.
  pymux-element = default.pymux.element;

  # The client library on its own, for a program that drives a server
  # and does not draw one. It is the one package here that carries no
  # toolkit and no parser.
  libpymux = default.libpymux;

  txterm = default.txterm;

  ptterm = default.ptterm;

  pyte = default.pyte;

  pyte-rs = default.pyte-rs;

  prompt-toolkit = default.prompt-toolkit;

  prompt-toolkit-rs = default.prompt-toolkit-rs;

  pymux-rs = default.pymux-rs;

  pysmithay = default.pysmithay;

  ptyhost = default.ptyhost;

  pyterm-pytest = default.pyterm-pytest;

  deferimport = default.deferimport;

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
  # judges: the log, and everything the suite left behind.
  # `nix/shared/suite.nix` says why the two are separate.
  checks = suites // {
    # Every suite that is a gate, at once. `checks.all.run` is the report:
    # each one's output linked by name, and a summary of how each ended.
    #
    # Twelve are left out, and none of them is a gate. The profile and
    # the latency measurement both read a wall clock, which says
    # nothing twice in a sandbox beside other jobs; they are
    # instrumentation, and reading them is the work. The image exercise
    # is baselined and green, but it stays a manual instrument: ten
    # minutes of seat time for six steps is worth spending when images
    # are touched, and not on every run. The fuzz hunt
    # finds deviations from kitty faster than they get fixed, so it
    # would fail this most days. The vttest walk draws screens for a
    # person to read and judges none of them. The pictures of vttest
    # judge a real terminal, and that part is not settled yet. The
    # pictures of pymux's chrome judge nothing at all yet, because
    # there is no recorded image to judge them against. The roaming
    # property tests draw a fresh example every run, which is the one
    # thing a gate may not do. The wire measurement prints sizes for
    # Lillecarl/pymux#258 and judges nothing.
    #
    # The shots of pymux-pictures are listed beside it, so the report's
    # times show where that check spends them.
    all = pkgs.callPackage ./nix/tests.nix {
      suites =
        pkgs.lib.mapAttrs' (
          terminal: shot: pkgs.lib.nameValuePair "pymux-pictures-${terminal}" { run = shot; }
        ) suites.pymux-pictures.shots
        // removeAttrs suites [
        "ptterm-fuzz"
        "ptterm-vttest"
        "pymux-chrome-pictures"
        "pymux-window-pane-pictures"
        "pymux-image-exercise"
        "pymux-latency"
        "pymux-profile"
        "pymux-scenarios"
        "pymux-theme-pictures"
        "pymux-vttest-pictures"
        "pymux-wire"
        "pyte-roaming"
      ];
    };
  };

  # Each source's docs site, and pyterm's own, which is the README with
  # a link to each source's. Lillecarl/pymux#671.
  docs =
    let
      build = pkgs.callPackage ./nix/docs { };
      textOf =
        src:
        lib.fileset.toSource {
          root = src;
          fileset = lib.fileset.unions (
            builtins.filter builtins.pathExists [
              (src + "/README.md")
              (src + "/docs")
              # The pictures a README shows.
              (src + "/images")
            ]
          );
        };
      source =
        name: modules:
        build {
          inherit name modules;
          src = textOf sources.${name};
          python = default.docsEnv name;
          links = lib.optional (name == "pymux") picturesLink;
        };
      picturesLink = {
        title = "The pictures";
        url = "https://lillecarl.github.io/pymux/pictures/";
      };
    in
    {
      pyte = source "pyte" [ "pyte" ];
      ptyhost = source "ptyhost" [ "ptyhost" ];
      ptterm = source "ptterm" [ "ptterm" ];
      txterm = source "txterm" [ "txterm" ];
      pymux = source "pymux" [ "pymux" ];
      pysmithay = source "pysmithay" [ "pysmithay" ];
      pyterm-pytest = source "pyterm-pytest" [ "pyterm_pytest" ];
      deferimport = source "deferimport" [ "deferimport" ];
      pyterm = build {
        name = "pyterm";
        src = textOf ./.;
        python = pkgs.python3.withPackages (p: [
          p.sphinx
          p.myst-parser
          p.furo
        ]);
        links =
          map (name: {
            title = name;
            url = "https://lillecarl.github.io/pyterm/${name}/";
          }) sourceNames
          ++ [ picturesLink ];
      };
    };

  # What a repository's Pages workflow deploys. A source's is its docs;
  # pymux's has the galleries under `pictures/` as well. pyterm's is its
  # own docs with each source's under `<name>/`, and never the
  # galleries: they take half an hour, so only pymux's repository builds
  # them.
  pages =
    lib.genAttrs sourceNames (name: docs.${name})
    // {
      pymux = pkgs.symlinkJoin {
        name = "pymux-pages";
        paths = [
          docs.pymux
          (pkgs.linkFarm "pymux-pictures" [
            {
              name = "pictures";
              path = pictures;
            }
          ])
        ];
      };
      pyterm = pkgs.symlinkJoin {
        name = "pyterm-pages";
        paths = [
          docs.pyterm
          (pkgs.linkFarm "pyterm-sources" (
            map (name: {
              inherit name;
              path = docs.${name};
            }) sourceNames
          ))
        ];
      };
    };

  sourceNames = [
    "pyte"
    "ptyhost"
    "ptterm"
    "txterm"
    "pymux"
    "pysmithay"
    "pyterm-pytest"
    "deferimport"
  ];

  # The galleries of everything pymux draws, laid out for a person to
  # read in a browser. The picture checks are galleries already -- runs
  # whose output is a tree of pictures beside their logs -- and this is
  # the page around them: one section per check.
  pictures = pkgs.callPackage ./nix/pictures.nix {
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
    # prompt-toolkit's copy of `nix/suite.nix`, which `sync-sources`
    # does not write, is the root's. Lillecarl/pymux#367.
    pyterm-one-suite-nix = pkgs.callPackage ./nix/one-suite-nix.nix {
      inherit sources;
    };
    # Each source's copy of `ruff.toml`, of `nix/suite.nix` and of the
    # rest of `nix/shared` is the root's.
    pyterm-sources-in-step = pkgs.callPackage ./nix/sources-in-step.nix {
      inherit sources sync-sources;
    };
    # The README names every check and every attribute here.
    # Lillecarl/pymux#475.
    pyterm-readme-names = pkgs.callPackage ./nix/readme-names.nix {
      readme = ./README.md;
      checks = lib.attrNames checks;
      # The keys of this file, read without evaluating a value.
      attributes = lib.attrNames (import ./. { inherit inputs system pkgs sourceOverrides; });
      skip = [
        # A scratch measurement, removed with Lillecarl/pymux#258.
        "pymux-wire"
        # What this file is built from, and what it builds the rest with.
        "pkgs"
        "sources"
        "suites"
        "default"
        "sourceNames"
      ];
    };
    # The mock the agent CLIs are driven against: the server comes up and
    # every wire format answers from a fixture. It gates the fixtures and the
    # package, not the agents -- their binaries are not this collection's to
    # pin.
    aimock-fixtures = pkgs.callPackage ./nix/agents/check.nix {
      inherit sources aimock;
    };
    pyte-unit = pyte.checks.unit;
    # The Rust kernels against the Python they replace.
    # Lillecarl/pymux#566.
    pyte-rs-parity = pyte-rs.checks.parity;
    prompt-toolkit-rs-parity = prompt-toolkit-rs.checks.parity;
    # Their Rust, held by rustfmt and clippy.
    pyte-rs-lint = pyte-rs.checks.lint;
    # pyte's suite with the Rust row in place of the dict.
    # Lillecarl/pymux#570.
    pyte-rs-unit = pyte-rs.checks.unit;
    # prompt-toolkit's suite with the Rust row in its composed screen.
    prompt-toolkit-rs-unit = prompt-toolkit-rs.checks.unit;
    prompt-toolkit-rs-lint = prompt-toolkit-rs.checks.lint;
    # pymux's image kernels, against its Python and in its style.
    # Lillecarl/pymux#574.
    pymux-rs-parity = pymux-rs.checks.parity;
    pymux-rs-lint = pymux-rs.checks.lint;
    # The compositor against real Wayland clients, its Rust's style, and
    # its Python's.
    pysmithay-unit = pysmithay.checks.unit;
    pysmithay-lint = pysmithay.checks.lint;
    pysmithay-ruff = pysmithay.checks.ruff;
    # The style of pyte: the selected lint rules, the layout at
    # width 120, and the future import in every file.
    pyte-ruff = pyte.checks.ruff;
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
    # The key encoder, judged against kitty's own, and each difference put
    # to kitty, Ghostty and WezTerm. Lillecarl/pymux#684.
    pyte-key-panel = pyte.checks.key-panel;
    # The pty layer, on its own. It runs real programs on real ptys,
    # and one of its tests holds it to importing nothing at all.
    ptyhost-unit = ptyhost.checks.unit;
    # The style of ptyhost: the selected lint rules, the layout at
    # width 120, and the future import in every file.
    ptyhost-ruff = ptyhost.checks.ruff;
    # The equipment the suites share: the seats, the drivers, the
    # budgets. Its own gate is the ceiling; the suites that use it are
    # the real judges.
    pyterm-pytest-unit = pyterm-pytest.checks.unit;
    # The style of pyterm-pytest.
    pyterm-pytest-ruff = pyterm-pytest.checks.ruff;
    # Lazy imports with no keyword: each mechanism against 3.15's own
    # answers, a probe each in a fresh interpreter. Twice, because the
    # mechanism follows the interpreter: 3.14 runs the proxies, 3.15 its
    # native lazy imports and the proxies.
    deferimport-unit = deferimport.checks.unit;
    deferimport-unit-315 = scopes.python315.deferimport.checks.unit;
    deferimport-ruff = deferimport.checks.ruff;
    # What a project outside pyterm gets from `deferimport/overlay.nix`.
    deferimport-nixpkgs = deferimport.checks.nixpkgs;
    deferimport-nixpkgs-315 = scopes.python315.deferimport.checks.nixpkgs;
    # The suite prompt-toolkit ships. ptterm and pymux are both built on
    # this fork, so a change to it that breaks the library breaks them,
    # and nothing here said so until this ran.
    prompt-toolkit-unit = prompt-toolkit.checks.unit;
    # Two, split by what they need. `ptterm-unit` needs nothing but
    # python, and it is seventeen of the thirty-six test files. The
    # tests that judge the screen rather than the widget moved to
    # `pyte-unit` and `pyte-xcms`. Lillecarl/pymux#11.
    ptterm-unit = ptterm.checks.unit;
    # The same unit suite on pyte's Rust row and kernels, which pymux
    # runs on. Lillecarl/pymux#470.
    ptterm-rs-unit = ptterm.checks.rs-unit;
    # The style of ptterm: the selected lint rules, the layout at
    # width 120, and the future import in every file.
    ptterm-ruff = ptterm.checks.ruff;
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
    # The style of txterm: the selected lint rules, the layout at
    # width 120, and the future import in every file.
    txterm-ruff = txterm.checks.ruff;
    # The conformance suite of xterm again, this time as a program in a
    # Textual widget. ptterm runs it on a bare pty with no toolkit, so
    # the two lists together say what a front end adds.
    txterm-esctest = txterm.checks.esctest;
    pymux-unit = pymux.checks.unit;
    # The compositor pymux holds for panes with no display, with the
    # `wayland` extra that every other pymux suite leaves out.
    # Lillecarl/pymux#383.
    pymux-wayland = pymux.checks.wayland;
    # Sound through a real PipeWire. Lillecarl/pymux#657.
    pymux-audio = pymux.checks.audio;
    # The types of pymux, held by a static checker rather than by a run:
    # a `Mode` member added and not handled by the `match` in
    # `run_pymux` fails here. Lillecarl/pymux#486.
    pymux-types = pymux.checks.types;
    # The style of pymux: the selected lint rules, the layout at
    # width 120, and the future import in every file. `ruff.toml`
    # in the root says what each rule is for.
    pymux-ruff = pymux.checks.ruff;
    # The `ssh://` client against a real openssh sshd, rather than the
    # asyncssh server that stands in for one everywhere else. It is the
    # only check that can say whether openssh agrees: the unix socket
    # channel every remote attach rests on, and the two directions a
    # port is forwarded in.
    pymux-openssh = pymux.checks.openssh-interop;
    # What it costs to lay a window out and draw the frame around its
    # panes, in bytecode instructions. The sibling of
    # `ptterm-instructions`, one layer up: that one measures what a
    # pane costs, and this one measures what arranging several of them
    # costs. It holds each count to a budget, so a change that makes a
    # frame much more expensive fails here instead of being felt later.
    pymux-frame = pymux.checks.frame;
    # What images cost, counted the same way: pyte reading a
    # transmission and drawing text over a placement, and pymux
    # cropping and re-encoding each image for a kitty and a sixel
    # client. Every count is taken in pure Python and again with the
    # Rust kernels, whose own work no count can see.
    pymux-images = pymux.checks.images;
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
    # That the declarations `<pymux-pane>` publishes are usable. The
    # element is TypeScript and the package build compiles it, so a type
    # that does not hold fails that build; this asks the question the
    # compiler cannot, with a consumer's own settings on the emitted
    # `.d.ts`. A compiler at build time, and nothing at run time.
    pymux-element = pymux.checks.element;
    pymux-pty = pymux.checks.pty;
    # The same end to end test, with the server and the client in one
    # process and no socket between them.
    pymux-integrated = pymux.checks.integrated;
    # A picture of a real terminal, with pymux in it and without it.
    # The result is a directory of pictures, so a run always leaves
    # something to look at.
    pymux-pictures = pymux.checks.pictures;
    # An image through a move and two resizes, photographed at each
    # step, in kitty and through a pane. Not a gate yet: nothing is
    # recorded against it, so the first runs are the evidence for the
    # issue they file, and only a recorded baseline can judge later
    # ones.
    pymux-image-exercise = pymux.checks.imageExercise;
    # The same picture, of vttest. Not a gate: the chain is proven and
    # the judging is not, and it is minutes of work for one item of
    # vttest's main menu.
    pymux-vttest-pictures = pymux.checks.vttestPictures;
    # yazi and claude-code, driven step by step, bare and through pymux at
    # once. Not a gate. Lillecarl/pymux#593.
    pymux-scenarios = pymux.checks.scenarios;
    # A picture of what pymux draws around a pane: the status line, a
    # title bar, the command palette, a strip. Not a gate either, and
    # it judges nothing: the chrome is the thing pymux adds, so there
    # is no bare side to subtract from. Reading the pictures is the
    # work. Lillecarl/pymux#161.
    pymux-chrome-pictures = pymux.checks.chromePictures;
    # A Wayland window in a pane, in every terminal. Lillecarl/pymux#620.
    pymux-window-pane-pictures = pymux.checks.windowPanePictures;
    # Every view before and after `upgrade-server`, in a real terminal,
    # and each pair has to be the same pixels. Lillecarl/pymux#408.
    pymux-upgrade-pictures = pymux.checks.upgradePictures;
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

  # What prompt-toolkit's own CI runs, and a stricter typing pass
  # over changed code, as programs on PATH instead of sandbox
  # verdicts. The checks above judge what nix builds; these judge the
  # checkout as it is, which is what an edit needs before it is committed,
  # and `prompt-toolkit-review` judges one upstream PR base against
  # head inside a throwaway sandbox the caller names.
  # `nix run --file . prompt-toolkit-ci`, from the prompt-toolkit
  # checkout. `./prompt-toolkit.nix` holds them because upstream cannot
  # take developer tooling for one person's fork.
  inherit (pkgs.callPackage ./prompt-toolkit.nix { inherit devEnv; })
    prompt-toolkit-ci
    prompt-toolkit-pyrefly
    prompt-toolkit-review
    ;

  devEnv = default.devEnv;

  shell = pkgs.callPackage ./pkgs/shell {
    inherit devEnv aimock;
  };
}
