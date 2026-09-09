# The model, and the words for it

Carl: "something I realize we need to work on is common terminology so
I know how to refer to different things ... I believe this will help
both me and you architect properly, currently we might be talking past
each other without knowing."

So this file is the shared vocabulary and the shape underneath it. It
is deliberately slim: what each layer is, what the objects are called,
and how one frame and one keystroke travel. It is not API
documentation, and it does not repeat what a module docstring says
better.

**Read `CLAUDE.md` for the rules of working here**, and `README.md` for
how to build and test. This file is only the model.

## The words that mean two things

These are the ones that cause a conversation to go wrong. When one of
them matters, say which.

| the word | here it means | and not |
| --- | --- | --- |
| **window** | a numbered tab of panes, `arrangement.Window`. tmux's window. | prompt_toolkit's `Window`, which is one widget that draws one thing; nor the window of the outer desktop |
| **screen** | what a program has drawn, `pyte.screen.Screen`: cells, cursor, modes, history | prompt_toolkit's `Screen`, which is the cells of **one frame** of one client |
| **layout** | where the panes are: `Divided`, `Strip`, `Zoomed` | prompt_toolkit's `Layout`, which owns the container tree and the focus; nor `pymux/layout.py`, which builds that tree |
| **terminal** | the widget that draws one program: `ptterm.Terminal` or `txterm.Terminal` | the terminal emulator pymux itself runs inside, which we call **the outer terminal** |
| **pane** | one program in one rectangle, `arrangement.Pane` | `libpymux.Pane`, which is a handle a script holds over a socket |
| **client** | one attached terminal: one `ClientState`, one prompt_toolkit `Application` | the `pymux` process a person typed, which is `pymux/client/` |
| **cell** | one character position on a screen, `pyte.cells.Cell` | a cell of a frame, which is prompt_toolkit's `Char` |

Two more that are easy to blur:

- **the server** is the `Pymux` object and the process holding it. **the
  session** is what that server holds: one `Arrangement`, its windows,
  and the options. One server, one session, several clients.
- **the frame** is one render for one client. **the plan** is where the
  panes are, which every client of one window shares.

## The words the layout engine uses

`pymux/docs/layout-engine-plan.md` holds the design. These are the
nouns, and they are worth learning because they are what a layout
question is asked in.

| the word | what it is |
| --- | --- |
| **plane** | the coordinate space the panes live on. Integer cells, unbounded: `x` and `y` may be negative |
| **rectangle** (`Rect`) | `x`, `y`, `width`, `height` on the plane. Cells, never fractions |
| **slot** (`Slot`) | the thing that *has* a rectangle. It owns one or more panes and shows one. More than one means tabbed |
| **plan** (`Plan`) | one answer to "where is everything": a rectangle per slot, plus the services -- `at`, `slot_of`, `neighbour`, `trace`, `reading_order` |
| **gap** | cells a layout leaves between two rectangles. A hole in the plan, and where a border goes |
| **chrome** | what fills a gap, as `Line`s. A pane knows nothing about borders; the layout says where they go and `PlanContainer` paints them |
| **view** (`View`) | the part of the plane one client sees: an offset and a size. One per client and window, held by `DynamicBody`, so it outlives the containers |
| **window-size** | which client's terminal a window's plane is sized by: `smallest`, `largest`, `latest`, or `manual`. The plan is shared, the views are not |
| **the bar above / the bar below** | the two title bars of a pane. The one above names the panes to its left and right; the one below names the panes above and below it |

So "the rectangle is split" means: this slot has a neighbour on that
side, because a split put one there. "The pane is stacked" means the
other thing -- one slot, two panes, one of them shown.

## The layers, and the one rule

Six packages. Each one claims one job, and **a layer may reach the
layers under it and never the ones above**. Three test files hold that
(`CLAUDE.md` names them).

    pyte          parse, and hold a screen          no I/O, no toolkit
    ptyhost       run a program on a pty            no toolkit
    ptterm        draw one terminal, prompt_toolkit
    txterm        draw one terminal, Textual
    pymux         arrange several of them
    prompt-toolkit  the toolkit under ptterm and pymux

`ptterm` and `txterm` are siblings and neither knows the other. They
are two front ends over the same screen.

**Almost none of this is inheritance.** The hierarchies below are
containment: what holds what. Inheritance appears in three places
only, and each is a framework asking for it: prompt_toolkit's
`Container` and `UIControl`, Textual's `Widget`, and the small
abstract bases pymux uses for its options, its clients and its pipes.

## pyte -- parse, and hold a screen

It takes the bytes a program writes and keeps what they mean. It draws
nothing, does no I/O, and has no opinion about how a cell is spelled
for a renderer. That is why two widgets can share it.

    Stream / ByteStream     parse: bytes -> "do this to the screen"
    Screen                  the state: cursor, modes, margins, titles,
                            what a program asked for
      Page                  the cells, and the history under them
        Row                 one row: a sparse dict of cells
        Cell                one character position (an appearance and
                            the text), and `LogicalLine` is the line
                            it belongs to before wrapping
      GraphicsState         images a program sent, for kitty graphics

The protocol lives in modules of its own, and none of them touch a
screen: `sequences.py` and `escape.py` spell sequences, `modes.py`,
`parameters.py`, `osc.py` and `keys.py` name what they carry,
`colors.py` and `xcms.py` do colour arithmetic, `terminfo.py` writes
the entry a pane is told about.

**The screen is where the history is**, so a scrollback is a `Page`
question and never a widget's. A resize reflows there too.

## ptyhost -- run a program on a pty

The smallest package. It opens a pty, starts a child on it, and
carries the bytes.

    Process     start, write_input, set_size, suspend, resume, kill,
                get_cwd, get_name, is_terminated

It knows nothing about screens or widgets: it hands bytes to a
callback. `record.py` is a tool built on it -- it records a real
program's output for the picture fixtures.

## ptterm -- draw one terminal, with prompt_toolkit

Three classes carry it, and one of them is for anybody outside.

    Terminal            the widget. A `FloatContainer` holding:
      terminal_window     the screen. A `_Window`, which keeps the
                          bottom of the screen in view from the
                          screen's own numbers, drawing
        _TerminalControl  a `UIControl`. It feeds the stream what the
                          program wrote, and turns the screen into the
                          rows prompt_toolkit asks for
      copy_window         what replaces the screen while a person
                          reads the history
      search_toolbar      searching that history

`Terminal` owns a `ptyhost.Process` and a `pyte.Screen`, and
`ptterm/style.py` spells a cell's `Appearance` as a prompt_toolkit
style string. That spelling is the whole of what this layer adds to a
cell.

## txterm -- draw one terminal, with Textual

The same joint, for the other toolkit.

    Terminal(Widget)    one terminal in a Textual app
    TerminalApp(App)    a whole app that is one of them

`txterm/style.py` builds a `rich.style.Style` where ptterm builds a
string. Everything under it -- the process, the screen, the history --
is the same code.

## pymux -- arrange several of them

The biggest one. Read it as three trees that meet in one container.

**What exists**, which every client shares:

    Pymux                   the server, and the session it holds
      Arrangement           every window, and which one each client is on
        Window              one numbered tab
          root              a tree of `VSplit` / `HSplit` of `Pane`
          column_widths     a strip's fractions
          zoom              whether one pane fills it
        Pane                one program in the window
          terminal          a `ptterm.Terminal`, so a process and a screen
      options               `set-option`, in `options.py`
      overlay_pane          `display-popup`, outside every window tree

**What one client has**, one of these per attached terminal:

    ClientState             one client
      app                   a prompt_toolkit `Application`
      layout_manager        `LayoutManager`: the whole screen of this
                            client, and the plan of the frame it is drawing
        DynamicBody         swaps in the body of the window this client
                            is on, and rebuilds it when the panes change
          PlanContainer     draws a plan: each pane at its rectangle,
                            less the offset of the view
      command_buffer        what a person types after ":"

**Where the panes go**, which is the layout engine:

    plane.py    Rect, Slot, Plan, View, Side, Line -- the geometry, and
                almost no behaviour. It imports two NamedTuples and
                nothing else
    tiling.py   the walk from a tree of splits to a plan, shared by
                the two layouts that have a tree
    divided.py  Divided -- an exact tiling of the plane. The default
    strip.py    Strip -- a row of columns that may be wider than the
                view, and scrolls. niri's model
    zoomed.py   Zoomed(inner) -- a wrapper: one pane fills the plane and
                what it wraps is untouched

Each layout answers three questions and there is no base class yet, on
purpose -- one written before the third subclass would be a guess:

    measure(plane) -> Plan          where the panes are
    chrome(plan) -> list[Line]      what fills the gaps it left
    look_at(plan, view, focus) -> Point   where the view goes

**The plan is measured for the plane, and drawn in the view.** Those
are one rectangle while every client is the same size, and two as soon
as they are not. `View.moved_onto` holds the three rules every layout
follows: a rectangle already in the view moves nothing, one too big to
show whole shows its start, and the view stays on the plane.

`Plane` and `Masonry` are the two that do not exist yet.

**The rest of pymux, by job**: `commands/` is every command a person
can type, `key_bindings.py` and `key_mappings.py` are the keyboard,
`format.py` is `#{...}`, `style.py` and `colors.py` are the theme,
`graphics.py` is images in panes, `server.py` and `pipes/` are the
socket, `client/` is the program a person runs to attach, and
`libpymux/` is a library for scripting a running server.

## How it comes together

One picture, and then three paths through it.

    the outer terminal: foot, kitty, xterm, ...
        |  keys                              ^  escape sequences
        v                                    |
    pymux client  (client/)                   |
        |                                     |
        +---- a socket, or nothing at all ----+
        |     ("pymux integrated" puts both ends in one process)
        v
    Pymux -- the server, and one session
        |
        +-- Arrangement -- every Window, and the tree of Panes in each
        |
        +-- ClientState, one per attached client
              |
              +-- Application (prompt_toolkit): the focus, the keys
              +-- LayoutManager: this client's whole screen
                    |
                    +-- DynamicBody -- the window this client is on
                    |     |
                    |     +-- PlanContainer -- draws a plan
                    |           ^
                    |           +-- Divided | Strip | Zoomed(inner)
                    |               measure() -> Plan: one Rect per Slot
                    |
                    +-- the status line, the message toolbar, the popups

    and in every pane, under all of it:

    ptterm.Terminal (or txterm.Terminal)
        |
        +-- pyte.Screen  <-- pyte.Stream  <-- ptyhost.Process  <-- the program

Three paths. Follow one at a time.

**A byte a program wrote, on its way to the outer terminal.** The
child writes to its pty; `ptyhost.Process` reads it and hands it to
`ptterm.Terminal`, which feeds `pyte.Stream`, which changes
`pyte.Screen`. The screen is now different, so pymux asks every client
for a frame (`Pymux.invalidate`). In that frame,
`_TerminalControl.create_content` turns the rows of the screen into
prompt_toolkit content, `ptterm/style.py` spells each cell, and
prompt_toolkit writes the cells of the frame into its own `Screen`.
The renderer compares that with the frame before it and writes the
difference to the outer terminal as escape sequences.

**A key a person pressed.** The outer terminal sends it to the client
process (`client/`), which forwards it over the socket (`pipes/`) to
the server. **The `Application` is on the server**, one per client, so
it is there that the bytes become a key press. `PymuxKeyBindings`
decides: the prefix and what follows it are pymux's own. Anything else
reaches the widget that has the focus, and `ptterm.Terminal`'s own
binding for any key writes it to the process
(`Screen.encode_key`, then `Process.write_input`), which is the pty,
which is the program.

That the `Application` lives on the server is the reason `pymux
integrated` exists: with both ends in one process there is no socket in
the middle, and a test can drive the client and read the server.

**One frame of one client.** `before_render` throws away the plan of
the frame before. The renderer walks the container tree of that
client: the background, then `DynamicBody`, which returns the body of
the window this client is on, and inside it `PlanContainer`. The
container asks its layout to `measure` a plan **for the plane**, asks
`look_at` where this client's view sits on it, paints the `chrome` into
the gaps, and writes each slot's shown pane at its rectangle less the
offset.

How big the plane is comes from `Pymux.the_size_of_the_plane`, which
reads the window's `window-size`. How much of it this client can see is
`LayoutManager.the_room_this_client_has`, which is its own terminal.
Two clients of different sizes therefore draw one plan and two views.

**The plan is also what sizes a pane.** A pane whose rectangle reaches
no part of the view is not drawn at all, and a program does not stop
needing to know how big it is, so the container tells every pane its
rectangle whether it draws it or not. It used to arrive through the
drawing -- prompt_toolkit hands a size to `create_content` -- and the
end to end checks are what noticed: a column scrolled off the left
kept reporting the size of the whole terminal. The title bars are floats
that draw last; each one asks `the_pane_beside`, which reads **the plan
this frame already measured**. Then the status line, the message
toolbar and any popup draw over the top, and the renderer diffs and
writes.

## The three numbers to know

- **A plan per frame is one.** Everything drawn in a frame asks the
  same geometry question, and `checks.pymux-frame` counts the answers.
- **A frame of eight panes is about 3.6 ms**, and the layout is a
  fifth of it. `checks.pymux-profile` says where the rest goes.
- **A pane keeps its history in `pyte`**, so a deep scrollback is a
  `Page`, not a widget. `checks.ptterm-instructions` measures what it
  costs at 2000, 10000 and 50000 rows.

## Where this file is wrong

It will go out of date, and a wrong map is worse than none. Two rules
keep it honest:

- It says **what a thing is and where it lives**, never how it works.
  A signature or a rule belongs in the module, next to the code.
- When a layer changes shape, this file changes in the same commit.
  `Plane` and `Masonry` landing is that kind of change, and so is the
  tree moving out of `arrangement.Window` into the layouts.
