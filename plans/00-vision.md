# Vision

## Why fork

[Syncplay](https://github.com/Syncplay/syncplay) is a mature tool that
synchronises playback across mpv / VLC / MPC across the internet. It has
been quietly excellent for a decade. The protocol is well-tested, the
sync algorithm (with `slowOnDesync` smoothing) is solid, the community
runs free public servers at `syncplay.pl`, and the codebase is small
enough to read end-to-end in an afternoon.

What hasn't aged as well is the user-facing surface:

- The chat window is a separate floating Qt window from your media
  player. Most people end up alt-tabbing between two windows for the
  entire movie.
- Chat messages, sync events ("user paused at 0:14:22"), and errors
  ("connection lost") all share the same text stream. Errors render in
  red and drown out conversation during a network blip.
- By default, every chat message also overlays onto the video as an
  OSD line. Some people like it; many find it disruptive.
- The settings dialog exposes every option Syncplay supports as a flat
  list. The four things people change regularly — audio track, subtitle
  track, subtitle delay, UI language — are not surfaced any differently
  from the dozens of options nobody touches.
- Each supported media player (VLC, mpv, MPC, MPC-BE, mplayer, IINA,
  memento, mpvnet) has its own adapter. That breadth is great, but it
  means the project's surface area is much larger than what most users
  ever exercise, and the player-launch UX is "find your player binary,
  point Syncplay at it."

## What we're keeping

The protocol layer (`syncplay/protocols.py`), the sync core
(`syncplay/client.py`), the server (`syncplay/server.py`), and the
configuration plumbing (`syncplay/ui/ConfigurationGetter.py`) are reused
unchanged. The community at `syncplay.pl` is reused unchanged. The
identity model is reused unchanged.

This is the load-bearing decision behind the fork: **we do not fragment
the network**. A `syncplay-modern` user dropping into a room alongside
upstream Syncplay users interoperates seamlessly, with no special server,
no special handshake, and no protocol divergence to maintain.

## What we're replacing

- The GUI shell (`syncplay/ui/gui.py`, `syncplay/ui/GuiConfiguration.py`)
  is replaced by a new single-window UI under `syncplay/ui/modern/`.
- The player adapters for everything-except-VLC (`syncplay/players/mpv.py`,
  `mpc.py`, `mpcbe.py`, `mplayer.py`, `iina.py`, `memento.py`, `mpvnet.py`,
  and the launch-external-VLC `vlc.py`) are removed. They are replaced by
  a single embedded-libvlc adapter (`syncplay/players/embedded_vlc.py`)
  that draws into a `QWidget` we own.

The user-visible consequence is that video and chat are in one window;
errors, sync events, and chat are visually distinct; and there is no
second player window to manage.

## Design principles

These are the rules that should guide future changes:

1. **Don't fork the protocol.** If a UI change requires a protocol
   change, the UI change is wrong. Surface the missing affordance some
   other way.
2. **Keep the rebase-with-upstream cadence cheap.** Anything that can
   live in `syncplay/ui/modern/` should live there. The upstream-touching
   files (`client.py`, `protocols.py`, `constants.py`,
   `ConfigurationGetter.py`) are kept upstream-compatible so we can pull
   protocol fixes quarterly without merge hell.
3. **Chat is for chat.** Errors get their own tab with a badge counter.
   Sync events render as subtle gray italic inline lines, not as red
   noise. The Chat tab only inserts a one-line `→ see Errors tab`
   pointer when an error fires.
4. **Sensible defaults beat sensible options.** Chat-on-video off by
   default. OSD off by default. The four common settings surfaced; the
   rest under collapsible Advanced.
5. **Focus-aware keybindings.** VLC-style shortcuts (`f`, `space`, arrows,
   `j/l`, `g/h`, `[/]`) attach to the video widget, not the application,
   so `space` in chat types a space.
6. **Cross-platform from day one.** Linux first because that's where the
   developer machine is, but the PyInstaller spec, the `videoWidget`
   native-handle plumbing (`set_hwnd` / `set_xwindow` / `set_nsobject`),
   and the libvlc plugin-path discovery are all written to work on
   Windows and macOS without restructure.

## What this fork is not

- **Not a new social network.** No accounts, no friend lists, no profiles.
  Rooms work the same way they always have.
- **Not a SaaS.** No hosted service. The community Syncplay servers are
  donated capacity; if usage grows, run your own.
- **Not a webapp.** It is a compiled desktop app. Wayland support is
  v2 territory; v1 forces XWayland on Linux because libvlc can't draw
  into a Wayland surface yet.
- **Not a player.** It is a sync client that happens to embed libvlc. The
  scope of player features is "what libvlc already does, exposed through
  the UI." We are not building format support, codec configuration,
  filter graphs, or anything VLC's own UI doesn't already do.
- **Not a Syncplay replacement.** It is a Syncplay client. Upstream
  Syncplay continues to exist, runs the servers, owns the protocol.
  This project is a UI fork, attributed under Apache 2.0, working name
  `syncplay-modern` until the public release picks a final name that
  doesn't use the "Syncplay" trademark per Apache 2.0 §6 courtesy.
