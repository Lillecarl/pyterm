{
  lib,
  src,
  buildPythonPackage,
  flit-core,
  wcwidth,
}:
buildPythonPackage {
  pname = "pyte";
  version = "0.8.3.dev";
  inherit src;
  pyproject = true;

  build-system = [ flit-core ];
  dependencies = [ wcwidth ];

  pythonImportsCheck = [ "pyte" ];

  meta = {
    description = "Simple VTXXX-compatible terminal emulator";
    homepage = "https://github.com/selectel/pyte";
    license = lib.licenses.lgpl3Only;
  };
}
