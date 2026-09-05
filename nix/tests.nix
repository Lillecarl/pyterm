# One report over every suite in the collection, and one gate.
#
# `checks.all` is the gate. `checks.all.run` is the report: a directory with
# every suite's own output linked under it, and a summary of how each one
# ended. The two are separate for the same reason every other check is (see
# `pyte/nix/suite.nix`): nix takes the output of a build that failed away, so
# a report that failed would take itself with it.
#
# `suites` is the checks of the collection, by name. Each one carries its run
# in `passthru.run`, and the report reads that.
{
  lib,
  runCommand,
  suites,
}:
let
  runs = lib.mapAttrs (_: check: check.run) suites;

  width = toString (
    lib.foldl' (widest: name: lib.max widest (lib.stringLength name)) 0 (
      lib.attrNames runs
    )
  );

  line =
    name: run: ''
      ln -s ${run} "$out/${name}"
      status="$(cat ${run}/status)"
      last="$(grep -v '^[[:space:]]*$' ${run}/log | tail -n 1 || true)"
      if [ "$status" = 0 ]; then
        mark="ok    "
      else
        mark="FAILED"
        worst=1
      fi
      printf '%-${width}s  %s  %s\n' "${name}" "$mark" "$last" \
        >> "$out/summary.txt"
    '';

  report = runCommand "pyterm-tests-run" { } ''
    mkdir -p "$out"
    : > "$out/summary.txt"
    worst=0
    ${lib.concatStringsSep "\n" (lib.mapAttrsToList line runs)}
    echo "$worst" > "$out/status"
    cat "$out/summary.txt"
  '';
in
runCommand "pyterm-tests" { passthru = { run = report; }; } ''
  cat ${report}/summary.txt
  if [ "$(cat ${report}/status)" != "0" ]; then
    echo "" >&2
    echo "A suite did not pass. Every one of them left its log and its" >&2
    echo "artifacts behind, linked by name under:" >&2
    echo "    ${report}" >&2
    exit 1
  fi
  touch "$out"
''
