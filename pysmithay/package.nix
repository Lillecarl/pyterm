# A headless Wayland compositor on Smithay, as a Python package.
#
# Not `mkProject`: that cuts the source down to `.py` files, and nixpkgs'
# Python set has no maturin. The wheel is built with the maturin program,
# offline, against crates vendored from `Cargo.lock`, and `pyprojectHook`
# installs it like any other.
#
# Linux only. Wayland's server side needs a Unix socket with SCM_RIGHTS
# and the shm pools a Linux client sends; nothing tries darwin yet.
{
  lib,
  stdenv,
  python,
  pyprojectHook,
  mkVirtualEnv,
  callPackage,
  rustPlatform,
  cargo,
  rustc,
  maturin,
  clippy,
  rustfmt,
  libxkbcommon,
  # The software renderer that composes a window with its popups.
  pixman,
  # The VP9 encoder of window panes. Lillecarl/pymux#639.
  libvpx,
  pkg-config,
  # Decodes the VP9 the encoder makes, in the tests.
  ffmpeg-headless,
  foot,
  wl-clipboard,
  dejavu_fonts,
  makeFontsConf,
  # The linter and formatter that the `ruff` check runs.
  ruff,
}:
let
  fs = lib.fileset;

  src = fs.toSource {
    root = ./.;
    fileset = fs.unions [
      ./Cargo.toml
      ./Cargo.lock
      ./build.rs
      ./pyproject.toml
      ./README.md
      ./LICENSE
      ./src
      ./python
    ];
  };

  cargoDeps = rustPlatform.importCargoLock { lockFile = ./Cargo.lock; };

  testEnv = mkVirtualEnv "pysmithay-test-env" {
    pysmithay = [ "test" ];
  };

  checks = callPackage ./nix/checks.nix {
    inherit
      python
      src
      cargoDeps
      testEnv
      rustPlatform
      cargo
      rustc
      clippy
      rustfmt
      ruff
      libxkbcommon
      pixman
      libvpx
      pkg-config
      ffmpeg-headless
      foot
      wl-clipboard
      dejavu_fonts
      makeFontsConf
      ;
  };

  pyproject = lib.importTOML ./pyproject.toml;
in
stdenv.mkDerivation {
  pname = "pysmithay";
  inherit (pyproject.project) version;

  inherit src cargoDeps;

  nativeBuildInputs = [
    pyprojectHook
    rustPlatform.cargoSetupHook
    cargo
    rustc
    maturin
    pkg-config
    rustPlatform.bindgenHook
  ];

  buildInputs = [
    libxkbcommon
    pixman
    libvpx
  ];

  # `--auditwheel skip`: a repair copies libvpx into the wheel without
  # the path to the libstdc++ it needs, and the module does not load.
  buildPhase = ''
    runHook preBuild
    maturin build --release --offline --frozen --auditwheel skip --interpreter ${python.interpreter} --out dist
    runHook postBuild
  '';

  passthru = {
    # What `mkProject` reads out of `pyproject.toml` for the others. The
    # names carry no version bound, so a name is the whole entry.
    dependencies = lib.genAttrs pyproject.project.dependencies (_: [ ]);
    optional-dependencies = lib.mapAttrs (
      _: names: lib.genAttrs names (_: [ ])
    ) pyproject.project.optional-dependencies;
    inherit checks;
  };

  meta = {
    description = "A headless Wayland compositor on Smithay, for Python";
    license = lib.licenses.mit;
    platforms = lib.platforms.linux;
  };
}
