# The shell this collection is worked in.
#
# `devEnv` is one virtualenv and it is the whole python: pymux, everything
# pymux declares, and the `test` extra that the suites and the hand-run
# drivers need. It carries `bin/pymux` as well, so there is no second python
# on PATH to shadow this one. Lillecarl/pymux#319.
{
  mkShell,
  runCommand,
  lib,
  devEnv,
  umbrella,
  # pkgs.jj is a JSON stream editor. jujutsu is the version control system.
  jujutsu,
  git,
  ruff,
  black,
  ncurses,
}:
let
  # A python program's programs, and nothing that says it is a python package.
  #
  # **One nixpkgs python package in `packages` puts every input on
  # PYTHONPATH**, the virtualenv included, and PYTHONPATH beats a venv's own
  # site-packages. So `/nix/store/<fresh>/bin/pymux` imported the shell's
  # pymux and ran code nobody built. Lillecarl/pymux#318.
  #
  # Measured 2026-09-13, by building one shell per input: the venv with
  # jujutsu, git, ruff and ncurses gives an empty PYTHONPATH; adding umbrella
  # gives seven entries and adding black gives ten, and in both the first
  # entry is the venv. The cause is nixpkgs' python setup hook, which a
  # `buildPythonApplication` brings in and which then adds the site-packages
  # of every input.
  #
  # A symlink to the wrapper keeps the program whole -- the wrapper sets its
  # own path and runs its own interpreter -- and carries none of that. It
  # also leaves the package alone, which umbrella needs: it stands on its
  # own, so other umbrella repositories can take it.
  justTheBinaries =
    pkg:
    runCommand "${lib.getName pkg}-bin" { } ''
      mkdir -p "$out"
      ln -s ${lib.getBin pkg}/bin "$out/bin"
    '';
in
mkShell {
  packages = [
    devEnv
    (justTheBinaries umbrella)
    (justTheBinaries black)
    jujutsu
    git
    ruff
    # tic and infocmp, for the terminfo entry of a pane.
    ncurses
  ];
}
