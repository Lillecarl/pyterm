# pysmithay

A headless Wayland compositor for Python, built on
[Smithay](https://github.com/Smithay/smithay) with PyO3.

It draws nothing. Each window's pixels come back to Python as RGBA, with
the rectangles the client damaged. The aim is to show a lightweight GUI
program inside a [pymux](https://github.com/Lillecarl/pymux) pane.

> This repository is a copy. Work on pysmithay happens in
> [pyterm](https://github.com/Lillecarl/pyterm), which exports its `pysmithay/`
> directory here on every push. Send changes there, and issues to
> [Lillecarl/pymux](https://github.com/Lillecarl/pymux/issues).
> `nix build github:Lillecarl/pysmithay` builds it from this repository alone.

Linux only.

## Use

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
            compositor.frame_done(0)   # let the client draw the next frame
```

The caller owns the event loop: wait for either descriptor in `fds()`
to become readable, then call `dispatch()`. Nothing blocks and no
thread starts.

| call | what it does |
| --- | --- |
| `dispatch()` | accept clients, run requests, return events |
| `frame(id)` | the window's last buffer, as `(width, height, rgba)` |
| `frame_done(time)` | tell every window its frame was shown |
| `configure(id, w, h)` | ask a window to take this size |
| `close(id)` | ask a window to close |
| `focus(id)` | give the keyboard to a window |
| `key(code, pressed, time)` | an evdev key code |
| `pointer_motion(id, x, y, time)` | in the window's surface pixels |
| `pointer_button(button, pressed, time)` | an evdev button code |

Events are tuples: `("toplevel", id)`, `("title", id, str)`,
`("app_id", id, str)`, `("commit", id, [(x, y, w, h), ...])` and
`("closed", id)`. A commit's damage is empty when it drew nothing; it
still waits on `frame_done`.

## What it does not do yet

- Subsurfaces and popups: only a window's own surface is read.
- Buffers other than wl_shm, so no GPU clients.
- Scroll, touch, clipboard and drag and drop.

## Checks

From the pyterm root:

    nix build --file . checks.pysmithay-unit checks.pysmithay-lint
