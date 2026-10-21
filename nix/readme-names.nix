# The README names every check and every attribute of `default.nix`.
#
# `CLAUDE.md` says to read the README first, so a check or a front end it
# leaves out is one nobody finds: `pymux-web` and `checks.pymux-element`
# were both missing until somebody went looking. Lillecarl/pymux#475.
#
# A check counts as named when `checks.<name>` appears, and an attribute when
# it appears in backquotes or after `--file .`. A name that is only a word in
# a sentence does not count: `pyte` is in every paragraph.
{
  lib,
  callPackage,
  readme,
  checks,
  attributes,
  # Names that need no entry, each with its reason beside it.
  skip,
}:
let
  inherit (callPackage ./shared/suite.nix { }) suite;

  # No `.` in the class: `checks.pymux-esctest.run` names `pymux-esctest`.
  after = "([^A-Za-z0-9_-]|$)";

  lookFor =
    patterns: name: ''
      if ! grep -qE ${lib.escapeShellArg patterns} ${readme}; then
        echo "  ${name}"
        missing=1
      fi
    '';

  checkLine = name: lookFor "checks\\.${name}${after}" "checks.${name}";
  attributeLine = name: lookFor "`${name}`|--file \\. ${name}${after}" name;

  wanted = names: lib.subtractLists skip names;
in
suite { name = "pyterm-readme-names"; } ''
  missing=0
  echo "Names README.md does not mention:"
  ${lib.concatMapStrings checkLine (wanted checks)}
  ${lib.concatMapStrings attributeLine (wanted attributes)}
  if [ "$missing" != 0 ]; then
    echo "Say what each one is for in README.md, or add it to the skip"
    echo "list of checks.pyterm-readme-names with the reason."
    exit 1
  fi
  echo "  none"
''
