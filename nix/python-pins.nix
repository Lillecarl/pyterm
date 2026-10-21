{
  fetchurl,
  unzip,
}:

/**
  The packages the collection needs newer than nixpkgs has, on every
  interpreter. A `packageOverrides` function: `default.nix` composes it
  into each python the collection supports, ahead of that python's own
  bends.

  # Type

  ```
  pins :: PythonPackages -> PythonPackages -> AttrSet
  ```
*/
_pyFinal: pyPrev: {
  # Async connections, and async callbacks that run on the event loop,
  # arrived in 3.52; 3.54 fixes leaks and crashes in error handling.
  # Lillecarl/pymux#722.
  #
  # **SQLite comes from apsw's own release, compiled into the
  # extension.** An apsw release is made for the SQLite of the same
  # number, and nixpkgs' `sqlite` is older. The amalgamation build
  # declares every SQLite symbol `static` (`src/apsw.c`, `SQLITE_API`),
  # so no other `libsqlite3.so.0` in the process -- the one Python's own
  # `sqlite3` loads -- can answer for it. The check below holds the
  # two version numbers equal to the patch.
  apsw = pyPrev.apsw.overridePythonAttrs (old: rec {
    version = "3.54.1.0";
    src = fetchurl {
      url = "https://github.com/rogerbinns/apsw/releases/download/${version}/apsw-${version}.tar.gz";
      hash = "sha256-BDdfCM8d+AlJ7reZIK0c3eCOYXp/0+VEKkUk7xw/Lsg=";
    };
    amalgamation = fetchurl {
      url = "https://sqlite.org/2026/sqlite-amalgamation-3540100.zip";
      hash = "sha256-CpyONDUtrUYAaqgoNtU4O/+dxryc5aYFU8Baow5q0fk=";
    };
    nativeBuildInputs = (old.nativeBuildInputs or [ ]) ++ [ unzip ];
    buildInputs = [ ];
    # `setup.py` builds against `sqlite3/sqlite3.c` when it is there.
    postPatch = (old.postPatch or "") + ''
      unzip -q ${amalgamation}
      mv sqlite-amalgamation-3540100 sqlite3
    '';
    checkPhase = ''
      runHook preCheck
      python -c '
      import apsw
      assert apsw.using_amalgamation, "apsw links a shared SQLite"
      assert apsw.apsw_version().startswith(apsw.sqlite_lib_version() + "."), (apsw.apsw_version(), apsw.sqlite_lib_version())
      '
      python -m apsw.tests
      runHook postCheck
    '';
  });
}
