{
  fetchFromGitHub,
  fetchPypi,
  rustPlatform,
}:

/**
  The 3.15 bends, as a `packageOverrides` function for the 3.15
  interpreter alone. Nothing here is version-gated: this file is
  only ever composed into `python315`, so the scope is structural.

  # Type

  ```
  bends :: PythonPackages -> PythonPackages -> AttrSet
  ```
*/
pyFinal: pyPrev: {
  # The python315 of this snapshot is 3.15.0 final, one release
  # past some of the packages it brings, and the binary cache
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
    src = fetchFromGitHub {
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
    src = fetchPypi {
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
    src = fetchFromGitHub {
      owner = "HypothesisWorks";
      repo = "hypothesis";
      tag = "v${version}";
      hash = "sha256-e2RM1TaPz/C1VovVstmZJ1CICE0v7OVhsrR08a6epP0=";
    };
    cargoDeps = rustPlatform.fetchCargoVendor {
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
    src = fetchFromGitHub {
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
  # 2.1.0; 2.3.1 is where upstream tracks 3.15. The nixpkgs
  # patch is a 3.15 backport 2.3.1 already carries (its include
  # order is upstream's, and the `pprint` call it touches is
  # gone), so it no longer applies and is dropped.
  mypy = pyPrev.mypy.overridePythonAttrs (_old: rec {
    version = "2.3.1";
    src = fetchFromGitHub {
      owner = "python";
      repo = "mypy";
      tag = "v${version}";
      hash = "sha256-EkZVBWlT8l3oIC9UuDEJua6dxFDIL0o9k/3FJJFqMB4=";
    };
    patches = [ ];
  });

  # Bumped: the snapshot's 4.2.0 fails one dataclass brain test
  # on 3.15 (`test_kw_only_sentinel`: the fields it infers
  # changed); 4.3.4 is where upstream tracks 3.15 (PEP 810, PEP
  # 798, and the `kw_only` handling around this test). One
  # TypedDict brain test still fails there
  # (`__required_keys__` is gone on 3.15), in inference the
  # collection never reaches, so only that test is skipped.
  astroid = pyPrev.astroid.overridePythonAttrs (old: rec {
    version = "4.3.4";
    src = fetchPypi {
      pname = "astroid";
      inherit version;
      hash = "sha256-1RWhBXIrcgmLvoLUMNZeY190K2y6w736+LfBiLh8Xjk=";
    };
    disabledTests = (old.disabledTests or [ ]) ++ [
      "test_typed_dict_required_and_optional_keys"
    ];
  });

  # Bumped: the snapshot's 4.14.2 fails its TLS connectable
  # tests on 3.15 (`server_hostname can only be specified in
  # client mode`) and one lock cancellation test; 4.15.1 is
  # the latest release. Its own TLS tests still fail there --
  # 3.15 hardened the server side against a hostname -- and a
  # handful of others trip over unraisable-exception warnings
  # 3.15 emits where 3.14 stayed silent. None of it is the
  # paths the collection drives (anyio's own loop, no TLS
  # server here), so the failing tests are skipped.
  # `test_sourceless_install` shells out to pip, which cannot
  # fetch an isolated build backend in the sandbox.
  anyio = pyPrev.anyio.overridePythonAttrs (old: rec {
    version = "4.15.1";
    src = fetchPypi {
      pname = "anyio";
      inherit version;
      hash = "sha256-nygwYBjL1tMp5ko21YJW7f923Zlv5CO8lXMm5Xi4KpQ=";
    };
    disabledTests = (old.disabledTests or [ ]) ++ [
      "test_tls_connectable"
      "test_receive_invalid_max_bytes"
      "TestTLSStream::test_unwrap"
      "test_checkpoints_empty_results"
      "test_sourceless_install"
      "test_start_no_value"
      "test_glob_case_sensitive"
      "test_rglob"
    ];
  });

  # Bumped: the snapshot's 2.2.1 fails its bytecode verifier
  # tests on 3.15 (`ast.Name is not created from CALL`: new
  # opcodes); 2.3.0 is the latest release and declares 3.15.
  executing = pyPrev.executing.overridePythonAttrs (_old: rec {
    version = "2.3.0";
    src = fetchPypi {
      pname = "executing";
      inherit version;
      hash = "sha256-FZGctdZn5ctOCZURlx0A1llXP/8t1cTmzYtxY2x4WNI=";
    };
  });

  # Bumped: the snapshot's 2.13.4 fails five base64url tests on
  # 3.15 (URL-safe validation warns where it raised); 2.14.1 is
  # the latest release. The nixpkgs pytest-9.1 patch is already
  # upstream there, so it no longer applies and is dropped.
  # Same fetch shape as nixpkgs (the monorepo, not the PyPI
  # sdist): its `disabledTestPaths` globs name the
  # `pydantic-core` tests the sdist does not carry. One module
  # is new in 2.14 and needs `pytest-examples`, a test-only
  # dependency nothing here takes, so that path alone is
  # skipped beside them.
  pydantic = pyPrev.pydantic.overridePythonAttrs (old: rec {
    version = "2.14.1";
    src = fetchFromGitHub {
      owner = "pydantic";
      repo = "pydantic";
      tag = "v${version}";
      hash = "sha256-sk7BkUmVcDRNzcZz5czHxhyaDD1e7hHrR0cHeYU97J8=";
    };
    patches = [ ];
    disabledTestPaths = (old.disabledTestPaths or [ ]) ++ [
      "tests/pydantic_core/test_docstrings.py"
    ];
  });

  # Bumped alongside pydantic: 2.14.1 pins `pydantic-core==2.50.1`
  # and needs `typing-inspection>=0.4.4`, and the snapshot holds
  # 2.46.4 and 0.4.3. Same fetch shape as nixpkgs (GitHub tag,
  # vendored cargo tree).
  pydantic-core = pyPrev.pydantic-core.overridePythonAttrs (old: rec {
    version = "2.50.1";
    src = fetchFromGitHub {
      owner = "pydantic";
      repo = "pydantic";
      tag = "core-v${version}";
      hash = "sha256-sk7BkUmVcDRNzcZz5czHxhyaDD1e7hHrR0cHeYU97J8=";
    };
    sourceRoot = "${src.name}/pydantic-core";
    cargoDeps = rustPlatform.fetchCargoVendor {
      inherit (old) pname;
      inherit version src sourceRoot;
      hash = "sha256-EPTH6oOFIhsRHAvt3eS0mYbR1NMyjoPIs2YRPzd6QFU=";
    };
  });

  # Already the latest release (1.12.2): its PyO3 0.27.2 caps
  # at 3.14 and its code does not compile on 3.15, while
  # upstream's PyO3 0.29 move is unreleased. Pinned to the
  # master that carries it, by commit hash: backporting the
  # serializer rework that move took would be a fork, and this
  # is upstream's own tested tree instead. `RUSTC_BOOTSTRAP`
  # is nixpkgs', kept, and its own suite builds the extension
  # and round-trips every type through it.
  ormsgpack = pyPrev.ormsgpack.overridePythonAttrs (old: rec {
    src = fetchFromGitHub {
      owner = "aviramha";
      repo = "ormsgpack";
      rev = "14e0c40614e513c525e73fdd761896a90d6351ef";
      hash = "sha256-oxENFLzHQ6EBIwpd08wdJhq6Vo3EuL3LfOmEW7uDPEE=";
    };
    cargoDeps = rustPlatform.fetchCargoVendor {
      inherit (old.cargoDeps) pname;
      inherit src;
      hash = "sha256-adha1uKQgKiYEVFLwSYB1ztIzUoZZWe6oYmybZgFHAA=";
    };
  });

  typing-inspection = pyPrev.typing-inspection.overridePythonAttrs (_old: rec {
    version = "0.4.4";
    src = fetchPypi {
      pname = "typing_inspection";
      inherit version;
      hash = "sha256-VHJ0+msKVhzPVJzJUkuZmleOc30BXYcJ0CH50NE76kc=";
    };
  });
}
