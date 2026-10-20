# A Python package set extension: `python.override { packageOverrides = ...; }`
# or `pythonPackagesExtensions` takes it. `overlay.nix` does the latter.
pyfinal: _pyprev: {
  deferimport = pyfinal.callPackage ./python-package.nix { };
}
