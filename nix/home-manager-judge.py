"""
Does pymux accept the file the home-manager module wrote?

`nix/home-manager-check.nix` evaluates the module and hands the generated
`~/.pymux.conf` to this. Here it goes through `source-file`, which is the
command pymux itself runs at startup, so a line that pymux would refuse is
refused here too.

Two things are read back. First `startup_errors`, which is where every
failed line of a configuration file lands (`pymux/main.py`, and
Lillecarl/pymux#38 for why it is kept rather than shown). Then the values
themselves, because a line can be accepted and still arrive wrong: a
quoted value that loses its trailing space is the case that matters, and
only reading the value back sees it.
"""

import shlex
import sys

from pymux.commands.commands import handle_command
from pymux.main import Pymux

#: What the check asked the module to write, and what each one has to be
#: once pymux has read it. The names on the left are attributes of `Pymux`
#: or of its arrangement; `read` says where to find each one.
EXPECTED = {
    "base-index": ("base_index", 1),
    "history-limit": ("history_limit", 5000),
    "mouse": ("enable_mouse_support", True),
    "mode-keys": ("mode_keys_vi_mode", True),
    "default-terminal": ("default_terminal", "xterm-256color"),
    # The one that holds a "#", a ":" and a trailing space. It says
    # whether the quoting survived the whole way.
    "status-left": ("status_left", "[#h:#S] "),
}


def read(pymux, name):
    "Where a value lands. `base-index` is the one that is not on Pymux."
    if name == "base_index":
        return pymux.arrangement.base_index
    return getattr(pymux, name)


def main(path):
    pymux = Pymux()
    handle_command(pymux, "source-file %s" % shlex.quote(path))

    problems = list(pymux.startup_errors)

    for option, (name, wanted) in sorted(EXPECTED.items()):
        got = read(pymux, name)
        if got != wanted:
            problems.append(
                "%s: pymux read %r, and the module asked for %r" % (option, got, wanted)
            )

    # The binding the check put in `extraConfig`. It proves that the lines
    # after the settings arrive as commands and not as text. The key of
    # `custom_bindings` is (needs prefix, key name).
    if (True, "|") not in pymux.key_bindings_manager.custom_bindings:
        problems.append("extraConfig: the bind-key line bound nothing")

    if problems:
        print("The generated configuration file is not one pymux accepts:")
        for problem in problems:
            print("  %s" % problem)
        print()
        print("The file it read:")
        with open(path) as f:
            for number, line in enumerate(f, start=1):
                print("  %3i  %s" % (number, line.rstrip("\n")))
        return 1

    print("pymux read every line of the generated configuration file.")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1]))
