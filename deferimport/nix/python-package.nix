# deferimport as a nixpkgs Python package, for a project outside pyterm.
# `overlay.nix` beside `default.nix` puts it in every Python package set.
#
# pyterm builds it with pyproject.nix instead (`package.nix`); this file is
# for a set that `buildPythonPackage` builds. `checks.deferimport-nixpkgs`
# runs the suite against it.
{
  lib,
  buildPythonPackage,
  hatchling,
}:
let
  project = (lib.importTOML ../pyproject.toml).project;
in
buildPythonPackage {
  pname = project.name;
  inherit (project) version;
  pyproject = true;

  src = lib.fileset.toSource {
    root = ../.;
    fileset = lib.fileset.unions [
      ../deferimport
      ../pyproject.toml
      ../README.md
      ../LICENSE
    ];
  };

  build-system = [ hatchling ];

  pythonImportsCheck = [ "deferimport" ];

  meta = {
    description = project.description;
    homepage = project.urls.Homepage;
    license = lib.licenses.bsd3;
  };
}
