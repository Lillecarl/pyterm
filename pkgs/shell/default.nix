{
  mkShell,
  python3,
  prompt-toolkit,
  pyte,
  ptterm,
  pymux,
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
    pymux
    umbrella
    jujutsu
    git
    ruff
    black
    # tic and infocmp, for the terminfo entry of a pane.
    ncurses

    # The four packages of this collection, and what their tests need. A
    # test runs against the source in the checkout, so the environment
    # carries the dependencies and not the packages under test.
    (python3.withPackages (ps: [
      prompt-toolkit
      pyte
      ptterm
      ps.docopt-ng
      ps.wcwidth
      ps.hypothesis
      ps.pytest
      ps.libtmux
      ps.pyinstrument
    ]))
  ];
}
