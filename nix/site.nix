# The site: the galleries of everything pymux draws, laid out for a
# person to read in a browser.
#
# The picture checks are galleries already -- runs whose output is a
# tree of pictures beside their logs -- and this is the page around
# them: one section per check, every picture inline, the run's log
# beside them. It exists so that the pictures are read without a
# checkout of the collection.
{
  stdenvNoCC,
  python3,
  # One section per picture check: its name in the address, the title
  # and the sentence it gets on the page, and the run whose output is
  # the gallery.
  sections,
}:
stdenvNoCC.mkDerivation {
  pname = "pymux-pictures";
  version = "0";

  nativeBuildInputs = [ python3 ];

  env = { sections = builtins.toJSON sections; };
  dontInstall = true;

  buildCommand = ''
    mkdir -p "$out"
    python3 ${./site.py} "$out"
  '';
}
