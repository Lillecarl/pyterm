# `flake.lock` for `default.nix`, through flake-compatish, so the flake and a
# build from the file read one lock.
#
# An ignored checkout at ./prompt-toolkit replaces its pin in place, with no
# store copy, so an edit there reaches the next build. Where the directory is
# missing the lock answers, with no warning: on a clone without it, and in a
# flake, which copies only what git tracks.
let
  lock = builtins.fromJSON (builtins.readFile ../flake.lock);
  # Through the root's input map: a second copy in the graph would rename
  # ours to `flake-compatish_2`.
  node = lock.nodes.${lock.nodes.${lock.root}.inputs.flake-compatish};
  flake-compatish = builtins.fetchTree node.locked;
in
import flake-compatish {
  source = ../.;
  overrides = {
    self = ../.;
    prompt-toolkit = ../prompt-toolkit;
  };
}
