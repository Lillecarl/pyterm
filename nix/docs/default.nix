# The docs site of one source, built with Sphinx. Lillecarl/pymux#671.
#
# Every source gets one written for it: its README, every page in
# its `docs/`, and an API reference of its modules.
{ stdenvNoCC }:
/**
  The HTML site of one source.

  # Inputs

  `name`
  : The source's name, and the site's title

  `src`
  : The source's directory

  `python`
  : A Python environment that holds the source's package with its
    `docs` extra: Sphinx imports the modules it documents

  `modules`
  : The top-level modules the API reference walks; empty for none

  `links`
  : Further entries for the site's contents, as `{ title, url }`
*/
{
  name,
  src,
  python,
  modules ? [ ],
  links ? [ ],
}:
stdenvNoCC.mkDerivation {
  pname = "${name}-docs";
  version = "0";
  inherit src;

  nativeBuildInputs = [ python ];

  env.docs = builtins.toJSON { inherit name modules links; };
  __structuredAttrs = true;

  buildPhase = ''
    runHook preBuild
    python ${./build.py} ${./.} "$out"
    runHook postBuild
  '';

  dontInstall = true;
  dontFixup = true;
}
