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

from pymux.commands import handle_command
from pymux.config import client_options_in
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
    # And the one that holds a single quote, which is the character the
    # quoting has to escape rather than only wrap.
    "status-right": ("status_right", "it's #h"),
}

#: What `clientSettings` asked for, and what the client has to take out
#: of the same file. The server reads these lines too and does nothing
#: with them: it has no client to set them on, which is the whole
#: reason they are a scope of their own. Lillecarl/pymux#223.
EXPECTED_FOR_CLIENT = [
    # A bare word, which is what most values are. The two below carry
    # the quoting; this one says a plain value arrives plain.
    # Lillecarl/pymux#340.
    ("name", "desk"),
    ("swap-light-and-dark-colors", "on"),
    ("theme", "grey"),
]


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
    # after the settings arrive as commands and not as text.
    if pymux.key_bindings_manager.binding_on("|", needs_prefix=True) is None:
        problems.append("extraConfig: the bind-key line bound nothing")

    # And the client's half of the same file.
    announced = sorted(client_options_in(path))
    if announced != EXPECTED_FOR_CLIENT:
        problems.append(
            "clientSettings: a client would announce %r, and the module "
            "asked for %r" % (announced, EXPECTED_FOR_CLIENT)
        )

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
