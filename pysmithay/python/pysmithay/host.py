"""
A compositor in a process of its own, which the process that started it
drives over a socket: `pysmithay.RemoteCompositor` on that end, the same
methods as a `Compositor`. Lillecarl/pyterm#1004.

This loop is Python, and routes each request; `Channel` carries it out
and does every encode and every frame byte natively, on worker threads.
A window manager in Python can run a loop like this one and choose what
to do with each request first.

    python -I -m pysmithay.host --fd N [--socket PATH] [--width W] [--height H] [--wait S]

The child ends when the parent closes the socket, and its windows with
it: a parent that wants them kept keeps the socket open, across an
`exec` too.
"""

from __future__ import annotations

import argparse
import selectors
import sys
import time

from pysmithay._native import Channel, Compositor

#: How long the child waits, by default, for a path that another
#: compositor holds: an upgrading server lets its compositor go only when
#: it exits. Lillecarl/pyterm#622.
BIND_SECONDS = 30.0
BIND_RETRY_SECONDS = 0.05


def command(
    fd: int, socket_name: str | None = None, width: int = 800, height: int = 600, wait: float = BIND_SECONDS
) -> list[str]:
    "What starts a child that speaks over `fd`; the caller passes `fd` to it."
    argv = [sys.executable, "-I", "-m", "pysmithay.host", "--fd", str(fd)]
    argv += ["--width", str(width), "--height", str(height), "--wait", "%g" % (wait,)]
    return argv if socket_name is None else [*argv, "--socket", socket_name]


def bind(socket_name: str | None, width: int, height: int, wait: float = BIND_SECONDS) -> Compositor:
    "A compositor on `socket_name`, once the path is free, for at most `wait` seconds."
    deadline = time.monotonic() + wait
    while True:
        try:
            return Compositor(socket_name, width, height)
        except OSError as error:
            if "in use" not in str(error) or time.monotonic() > deadline:
                raise
        time.sleep(BIND_RETRY_SECONDS)


def serve(channel: Channel, compositor: Compositor) -> None:
    "Answer the parent and run the compositor, until the parent goes."
    with selectors.DefaultSelector() as selector:
        selector.register(channel.fileno(), selectors.EVENT_READ, channel)
        for fd in compositor.fds():
            selector.register(fd, selectors.EVENT_READ, compositor)
        while True:
            woken = {key.data for key, _events in selector.select()}
            if channel in woken:
                requests, alive = channel.requests()
                for request in requests:
                    channel.answer(compositor, request)
                if not alive:
                    return
            if compositor in woken:
                channel.forward(compositor)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="pysmithay.host", description=__doc__.split("\n\n")[0])
    parser.add_argument("--fd", type=int, required=True, help="the socket to the parent")
    parser.add_argument("--socket", help="where to listen; the first free wayland-N when left out")
    parser.add_argument("--width", type=int, default=800)
    parser.add_argument("--height", type=int, default=600)
    parser.add_argument("--wait", type=float, default=BIND_SECONDS, help="seconds to wait for a path in use")
    args = parser.parse_args(argv)

    channel = Channel(args.fd)
    try:
        compositor = bind(args.socket, args.width, args.height, args.wait)
    except OSError as error:
        channel.failed(str(error))
        return 1
    channel.hello(compositor)
    try:
        serve(channel, compositor)
    finally:
        compositor.shutdown()
    return 0


if __name__ == "__main__":
    sys.exit(main())
