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
  foot,
  wl-clipboard,
  dejavu_fonts,
  makeFontsConf,
}:
let
  fs = lib.fileset;

  inherit (callPackage ./nix/suite.nix { }) suite;

  src = fs.toSource {
    root = ./.;
    fileset = fs.unions [
      ./Cargo.toml
      ./Cargo.lock
      ./pyproject.toml
      ./src
      ./python
    ];
  };

  cargoDeps = rustPlatform.importCargoLock { lockFile = ./Cargo.lock; };

  # The Rust's style, held by the formatter and by clippy with every
  # warning an error.
  #
  #     nix build --file . checks.pysmithay-lint
  checks.lint = suite {
    name = "pysmithay-lint";
    # A compiler, for the build scripts of the crates: a `runCommand`
    # has none of its own.
    inputs = [
      cargo
      rustc
      clippy
      rustfmt
      stdenv.cc
    ];
    setup = ''
      cp -r ${src}/. crate
      chmod -R +w crate
      cd crate
      export HOME="$TMPDIR"
      export PYO3_PYTHON=${python.interpreter}
      export CARGO_TARGET_DIR="$TMPDIR/target"
      export LIBRARY_PATH=${libxkbcommon}/lib:${pixman}/lib
      # What `cargoSetupHook` writes, which a `runCommand` never runs.
      mkdir -p .cargo
      printf '[source.crates-io]\nreplace-with = "vendored"\n[source.vendored]\ndirectory = "%s"\n' ${cargoDeps} > .cargo/config.toml
    '';
  } ''
    cargo fmt --check
    cargo clippy --offline --frozen -- -D warnings
  '';

  testEnv = mkVirtualEnv "pysmithay-test-env" {
    pysmithay = [ "test" ];
  };

  # The compositor against a client that draws known pixels, against
  # foot, a real program, and the clipboard against wl-copy and wl-paste.
  #
  #     nix build --file . checks.pysmithay-unit
  checks.unit = suite {
    name = "pysmithay-unit";
    inputs = [
      testEnv
      foot
      wl-clipboard
    ];
    env.FONTCONFIG_FILE = makeFontsConf { fontDirectories = [ dejavu_fonts ]; };
    setup = ''
      cp -r ${./tests} tests
      chmod -R +w tests
      export HOME="$TMPDIR"
      export LANG=C.UTF-8
      export PYTHONDONTWRITEBYTECODE=1
    '';
  } "python -m pytest tests -q -p no:cacheprovider";
in
stdenv.mkDerivation {
  pname = "pysmithay";
  version = "0.1.0";

  inherit src cargoDeps;

  nativeBuildInputs = [
    pyprojectHook
    rustPlatform.cargoSetupHook
    cargo
    rustc
    maturin
  ];

  buildInputs = [
    libxkbcommon
    pixman
  ];

  buildPhase = ''
    runHook preBuild
    maturin build --release --offline --frozen --interpreter ${python.interpreter} --out dist
    runHook postBuild
  '';

  passthru = {
    dependencies = { };
    optional-dependencies.test = {
      pytest = [ ];
      pywayland = [ ];
    };
    inherit checks;
  };

  meta = {
    description = "A headless Wayland compositor on Smithay, for Python";
    license = lib.licenses.mit;
    platforms = lib.platforms.linux;
  };
}
