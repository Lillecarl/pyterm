# The shell this collection is worked in.
#
# `devEnv` is one virtualenv and it is the whole python: pymux, everything
# pymux declares, and the `test` extra that the suites and the hand-run
# drivers need. It carries `bin/pymux` as well, so there is no second python
# on PATH to shadow this one and no PYTHONPATH to put an older copy in front
# of a freshly built package. Lillecarl/pymux#318, Lillecarl/pymux#319.
#
# A suite still runs against the source in the checkout, because a run starts
# in that repository and its own directory comes first.
{
  mkShell,
  devEnv,
  umbrella,
  # pkgs.jj is a JSON stream editor. jujutsu is the version control system.
  jujutsu,
  git,
  ruff,
  black,
  ncurses,
}:
mkShell {
  packages = [
    devEnv
    umbrella
    jujutsu
    git
    ruff
    black
    # tic and infocmp, for the terminfo entry of a pane.
    ncurses
  ];
}
