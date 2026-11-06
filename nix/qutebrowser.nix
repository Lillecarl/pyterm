/**
  qutebrowser from Lillecarl/qutebrowser, which carries our patches on top
  of the release that nixpkgs packages. `checks.pymux-browsers` drives it,
  and croshome installs it, so the browser a person runs is the one tested.
*/
{
  qutebrowser,
  python3Packages,
  src,
}:
qutebrowser.overrideAttrs (old: {
  inherit src;
  # The release tarball carries the generated help pages; a git tree does not.
  nativeBuildInputs = old.nativeBuildInputs ++ [ python3Packages.pygments ];
  preBuild = (old.preBuild or "") + ''
    python3 scripts/asciidoc2html.py
  '';
})
