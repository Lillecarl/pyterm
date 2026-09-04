{
  lib,
  src,
  buildPythonPackage,
  setuptools,
  wcwidth,
}:
buildPythonPackage {
  pname = "prompt-toolkit";
  version = "3.0.52";
  inherit src;
  pyproject = true;

  build-system = [ setuptools ];
  dependencies = [ wcwidth ];

  pythonImportsCheck = [ "prompt_toolkit" ];

  meta = {
    description = "Library for building powerful interactive command line applications";
    homepage = "https://github.com/prompt-toolkit/python-prompt-toolkit";
    license = lib.licenses.bsd3;
  };
}
