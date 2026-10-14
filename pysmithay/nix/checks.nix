# The suites that judge pysmithay. They declare their own inputs, so
# `package.nix` holds the package and carries nothing that only a test
# needs. `nix/suite.nix` says why a check is two derivations.
{
  lib,
  stdenv,
  callPackage,
  python,
  # The source the wheel is built from, and the crates it vendors.
  src,
  cargoDeps,
  # The python the suite runs on: pysmithay and its `test` extra.
  testEnv,
  rustPlatform,
  cargo,
  rustc,
  clippy,
  rustfmt,
  ruff,
  libxkbcommon,
  pixman,
  libvpx,
  pkg-config,
  # Decodes the VP9 the encoder makes.
  ffmpeg-headless,
  foot,
  wl-clipboard,
  dejavu_fonts,
  makeFontsConf,
}:
let
  inherit (callPackage ./suite.nix { }) suite;

  tests = lib.fileset.toSource {
    root = ../.;
    fileset = lib.fileset.unions [
      ../tests
      ../python
      ../pyproject.toml
    ];
  };
in
{
  # The Rust's style, held by the formatter and by clippy with every
  # warning an error.
  #
  #     nix build --file . checks.pysmithay-lint
  lint = suite {
    name = "pysmithay-lint";
    # A compiler, for the build scripts of the crates: a `runCommand`
    # has none of its own.
    inputs = [
      cargo
      rustc
      clippy
      rustfmt
      stdenv.cc
      pkg-config
      rustPlatform.bindgenHook
    ];
    setup = ''
      cp -r ${src}/. crate
      chmod -R +w crate
      cd crate
      export HOME="$TMPDIR"
      export PYO3_PYTHON=${python.interpreter}
      export CARGO_TARGET_DIR="$TMPDIR/target"
      export LIBRARY_PATH=${libxkbcommon}/lib:${pixman}/lib
      export PKG_CONFIG_PATH=${lib.getDev libvpx}/lib/pkgconfig
      # What `cargoSetupHook` writes, which a `runCommand` never runs.
      mkdir -p .cargo
      printf '[source.crates-io]\nreplace-with = "vendored"\n[source.vendored]\ndirectory = "%s"\n' ${cargoDeps} > .cargo/config.toml
    '';
  } ''
    cargo fmt --check
    cargo clippy --offline --frozen -- -D warnings
  '';

  # The compositor against a client that draws known pixels, against
  # foot, a real program, and the clipboard against wl-copy and wl-paste.
  #
  #     nix build --file . checks.pysmithay-unit
  unit = suite {
    name = "pysmithay-unit";
    inputs = [
      testEnv
      foot
      wl-clipboard
      ffmpeg-headless
    ];
    env.FONTCONFIG_FILE = makeFontsConf { fontDirectories = [ dejavu_fonts ]; };
    setup = ''
      cp -r ${tests}/tests tests
      chmod -R +w tests
      export HOME="$TMPDIR"
      export LANG=C.UTF-8
      export PYTHONDONTWRITEBYTECODE=1
    '';
  } "python -m pytest tests -q -p no:cacheprovider";

  # The Python's style: the selected rules, the layout at width 120, and
  # the future import in every file. `ruff.toml` in the pyterm root says
  # what each rule is for.
  #
  #     nix build --file . checks.pysmithay-ruff
  ruff = suite {
    name = "pysmithay-ruff";
    inputs = [ ruff ];
    setup = ''
      cp -r ${tests}/. .
      chmod -R +w .
    '';
  } ''
    export RUFF_CACHE_DIR="$TMPDIR/ruff"
    ruff check python tests
    ruff format --check python tests
    missing=$(grep -rL '^from __future__ import annotations' --include='*.py' --exclude-dir='.*' --exclude-dir='__pycache__' python tests || true)
    if [ -n "$missing" ]; then
      echo "files without the future import:"
      echo "$missing"
      exit 1
    fi
  '';
}
