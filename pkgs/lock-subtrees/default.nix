# Writes or checks the `flake.lock` of each source. `lock_subtrees.py` says
# how. It runs the caller's nix, so the lock is computed by the nix that
# reads it.
{
  writeShellApplication,
  python3,
  git,
  jujutsu,
}:
writeShellApplication {
  name = "lock-subtrees";
  runtimeInputs = [
    python3
    git
    jujutsu
  ];
  text = ''exec python3 ${./lock_subtrees.py} "$@"'';
}
