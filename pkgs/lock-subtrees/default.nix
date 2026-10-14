# Writes or checks the `flake.lock` of each source. `lock_subtrees.py` says
# how. It runs the caller's nix, so the lock is computed by the nix that
# reads it.
{
  lib,
  writers,
  git,
  jujutsu,
}:
writers.writePython3Bin "lock-subtrees" {
  makeWrapperArgs = [
    "--prefix"
    "PATH"
    ":"
    (lib.makeBinPath [
      git
      jujutsu
    ])
  ];
  # ruff.toml holds the style, at width 120.
  flakeIgnore = [ "E501" ];
} ./lock_subtrees.py
