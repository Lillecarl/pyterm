# pysmithay

> This repository is a copy. Work on pysmithay happens in
> [pyterm](https://github.com/Lillecarl/pyterm), which exports its `pysmithay/`
> directory here on every push. Send changes there, and issues to
> [Lillecarl/pymux](https://github.com/Lillecarl/pymux/issues).
> The docs are at <https://lillecarl.github.io/pysmithay/>.

<!-- The lines above are pyterm's nix/shared/readme-head.md, written by sync-sources. -->

A headless Wayland compositor for Python, built on
[Smithay](https://github.com/Smithay/smithay) with PyO3. Linux only.

It draws nothing. Each window's pixels come back to Python as RGBA, with
the rectangles the client damaged. It is how a GUI program shows inside
a [pymux](https://github.com/Lillecarl/pymux) pane.

```python
import select
from pysmithay import Compositor

compositor = Compositor()          # listens on $XDG_RUNTIME_DIR/wayland-N
print(compositor.socket_name)      # give this to a client as WAYLAND_DISPLAY

while True:
    select.select(compositor.fds(), [], [])
    for event in compositor.dispatch():
        if event[0] == "commit":
            _, window, damage = event
            width, height, rgba = compositor.frame(window)
            compositor.frame_done(window, 0)   # let it draw the next frame
```

The caller owns the event loop: wait for either descriptor in `fds()`
to become readable, then call `dispatch()`. The dispatch path blocks
nothing and starts no thread. The API reference on the docs site lists
every call: input, popups, scale, the clipboard, and `Vp9Encoder`,
which encodes a window's frames for a pane (frame encoding uses
worker threads).

Events are tuples, such as `("toplevel", id, tag)`,
`("commit", id, [(x, y, w, h), ...])` and `("closed", id)`. A commit's
damage is empty when it drew nothing, and it still waits on
`frame_done`. `Compositor.dispatch` lists them all.

## What it does not do yet

- Buffers other than wl_shm, so no GPU clients.
- Touch, and drag and drop.

<!-- The lines below are pyterm's nix/shared/readme-tail.md, written by sync-sources. -->

## Building

    nix build github:Lillecarl/pysmithay    # from this repository alone
    nix build --file . pysmithay            # in a checkout of pyterm

The suites that judge it run in pyterm, as `checks.pysmithay-*`.

## The collection

pysmithay is one source of [pyterm](https://github.com/Lillecarl/pyterm), and
each source claims one job:

| source | job |
| --- | --- |
| [pyte](https://lillecarl.github.io/pyte/) | parse, and hold a screen |
| [ptyhost](https://lillecarl.github.io/ptyhost/) | run a program on a pty, and carry its bytes |
| [ptterm](https://lillecarl.github.io/ptterm/) | draw one terminal, with prompt-toolkit |
| [txterm](https://lillecarl.github.io/txterm/) | draw one terminal, with Textual |
| [pymux](https://lillecarl.github.io/pymux/) | arrange several of them |
| [pysmithay](https://lillecarl.github.io/pysmithay/) | a headless Wayland compositor, for a GUI program in a pane |
| [pyterm-pytest](https://lillecarl.github.io/pyterm-pytest/) | the test equipment the suites share |
| [deferimport](https://lillecarl.github.io/deferimport/) | make imports lazy, without a keyword |

[pyterm's site](https://lillecarl.github.io/pyterm/) holds every source's
docs.
