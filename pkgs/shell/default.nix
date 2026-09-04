{
  mkShell,
  pymux,
  umbrella,
  # pkgs.jj is a JSON stream editor. jujutsu is the version control system.
  jujutsu,
  git,
}:
mkShell {
  packages = [
    pymux
    umbrella
    jujutsu
    git
  ];
}
