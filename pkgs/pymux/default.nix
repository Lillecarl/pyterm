{
  lib,
  src,
  buildPythonPackage,
  setuptools,
  prompt-toolkit,
  ptterm,
  docopt-ng,
}:
buildPythonPackage {
  pname = "pymux";
  version = "0.15";
  inherit src;
  pyproject = true;

  # pymux carries no pyproject.toml, so the build backend is named here.
  build-system = [ setuptools ];
  dependencies = [
    prompt-toolkit
    ptterm
    # docopt-ng is the maintained fork, and imports as docopt.
    docopt-ng
  ];

  pythonImportsCheck = [ "pymux" ];

  meta = {
    description = "Terminal multiplexer built on prompt_toolkit";
    homepage = "https://github.com/prompt-toolkit/pymux";
    license = lib.licenses.bsd3;
    mainProgram = "pymux";
  };
}
