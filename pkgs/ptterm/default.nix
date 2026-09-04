{
  lib,
  src,
  buildPythonPackage,
  setuptools,
  prompt-toolkit,
  pyte,
}:
buildPythonPackage {
  pname = "ptterm";
  version = "0.1";
  inherit src;
  pyproject = true;

  # Only ruff configuration lives in ptterm's pyproject.toml, so the build
  # backend has to be named here rather than read from it.
  build-system = [ setuptools ];
  dependencies = [
    prompt-toolkit
    pyte
  ];

  pythonImportsCheck = [ "ptterm" ];

  meta = {
    description = "Terminal emulator for prompt_toolkit";
    homepage = "https://github.com/prompt-toolkit/ptterm";
    license = lib.licenses.bsd3;
  };
}
