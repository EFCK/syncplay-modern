# Contributing

Thanks for taking an interest. This is a fork of
[Syncplay](https://github.com/Syncplay/syncplay) that replaces the GUI
and player adapter with a single-window UI and embedded libvlc; the
protocol layer and sync core are reused from upstream.

## Development setup

```bash
git clone https://github.com/<you>/syncplay-modern.git
cd syncplay-modern
uv venv
uv pip install -e . pyinstaller
.venv/bin/python syncplayClient.py --name dev --room debug
```

Requires VLC installed on the system (`libvlc.so.5` / `libvlc.dll` /
`libvlc.dylib`). The standard VLC install supplies it.

## Repo layout

- `syncplay/ui/modern/` — the new UI. Qt-free `events.py` and
  `messageRouter.py` are unit-testable without spinning up
  `QApplication`; everything else is Qt widgets.
- `syncplay/players/embedded_vlc.py` — libvlc adapter. Read the module
  docstring before touching it: libvlc event callbacks fire on libvlc
  worker threads and **must** be marshaled back via
  `reactor.callFromThread` before they touch the client or any Qt
  widget.
- `syncplay/client.py`, `syncplay/protocols.py`, `syncplay/constants.py`,
  `syncplay/ui/ConfigurationGetter.py` — **kept upstream-compatible**.
  Avoid edits here when an equivalent change can live in
  `syncplay/ui/modern/` instead. This keeps the rebase cadence (below)
  cheap.
- `build/` — packaging. `syncplay-modern.spec` is the PyInstaller spec;
  `build-linux.sh` wraps it.
- `docs/superpowers/specs/` — the design document this implementation
  follows. New work that diverges should update the spec first.

## Tracking upstream

Upstream Syncplay is added as a git remote named `upstream`:

```bash
git remote -v
# upstream  https://github.com/Syncplay/syncplay.git (fetch)
```

Plan to rebase / merge upstream's `protocols.py`, `client.py`, and
`constants.py` updates roughly **once a quarter**. Upstream changes
those files maybe a few times a year, mostly small fixes. The UI files
we deleted (`ui/gui.py`, `ui/GuiConfiguration.py`) and the player
adapters we deleted (`players/{mpv,mpc,…}.py`) will produce conflicts
on rebase — drop them, since the fork doesn't use them.

```bash
git fetch upstream
git rebase upstream/master      # or merge, depending on your workflow
# resolve conflicts in protocols.py / client.py if any
# delete-as-conflicted: anything under syncplay/ui/gui.py or the
# upstream player adapters
```

## Tests

Most behaviour is verified with headless QApplication scripts driven by
`QtTest.QTest`. See the commit messages for the existing phases — each
has a verification block describing what was exercised. There is no
formal test suite yet; that's a contribution that would be very
welcome.

For protocol-level changes the highest-value test is the two-instance
smoke test against `syncplay.pl`: spin up two clients in the same room
with `--name`/`--room`, give them an SYNCPLAY_AUTOCHAT_MSG /
SYNCPLAY_AUTOCHAT_AFTER_S to exchange chat, and verify the round-trip
in the logs.

## Coding style

- Match the surrounding file. The new modules under
  `syncplay/ui/modern/` use ~4-space indent, type hints on public
  surfaces, dataclasses for value types.
- Keep the message router Qt-free so it stays unit-testable.
- Prefer module-level functions for protocol-style hooks
  (`set_video_widget`, `set_fileinfo_sink`) over passing state through
  many constructors.

## Commits

Plain commit messages, no `Co-Authored-By` trailers. Use a short
imperative subject + a body that explains *why*. The existing commit
log is a fine reference for tone and detail level.

## Licensing

Apache 2.0. New files should carry an Apache 2.0 header pointing at
`LICENSE`. Files lightly touched from upstream keep their original
copyright header.

## Things known to be missing / wanted

- Verified Windows / macOS PyInstaller builds (we ship a spec but
  haven't tested those platforms).
- A real test suite (pytest) wrapping the headless scripts.
- A playlist UI (currently `sharedPlaylistEnabled` defaults to False;
  re-enabling it requires building the panel).
- A toast widget for in-video notifications when
  `chatOnVideoEnabled=True` (Phase 4 added the toggle but the rendering
  half is still a no-op).
- Wayland-native libvlc output (we force XWayland for v1).

If you tackle any of these, please update the relevant section of
`docs/superpowers/specs/` so it doesn't drift from the implementation.
