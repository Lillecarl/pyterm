"""
A backend that starts no program.

`Process` needs one, and a test of the drawing wants the widget without
a child on a pty: nothing forks, so nothing has to be waited for or
cleaned up. What the screen would have read is fed to `stream` by hand.

This is ptterm's `tests/no_backend.py` with the two things `Process`
asks of a backend that ptterm's widget never needed: a future that says
the program ended, and a `kill`.
"""

import asyncio

__all__ = ("NoBackend",)


class NoBackend:
    "The whole of the backend interface, doing nothing."

    def __init__(self) -> None:
        #: Every size the widget asked for, oldest first.
        self.sizes = []
        #: Every answer the screen sent back. A screen replies to a
        #: query, so a backend that cannot take an answer stops the run.
        self.written = []
        #: Whether there is anything more to read. Nothing here ever
        #: writes, so there never is and never was.
        self.closed = False
        #: The program ending. `Process` hangs a callback on it, and
        #: nothing here ever sets it.
        self.ready_f = asyncio.get_event_loop().create_future()

    def write_text(self, text: str) -> None:
        self.written.append(text)

    def add_input_ready_callback(self, callback) -> None:
        pass

    def set_size(self, width: int, height: int) -> None:
        self.sizes.append((width, height))

    def start(self) -> None:
        pass

    def connect_reader(self) -> None:
        pass

    def disconnect_reader(self) -> None:
        pass

    def kill(self) -> None:
        self.closed = True
