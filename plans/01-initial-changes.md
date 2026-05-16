# Initial changes (v0.1.0-alpha)

This is the record of what shipped in the first cut, broken down by the
eight implementation phases. Each phase is a single commit on `master`;
the tag `v0.1.0-alpha` marks the end of Phase 8.

The shared theme across all phases: **upstream-touching files stay
upstream-compatible**, and everything new lives under
`syncplay/ui/modern/` or `syncplay/players/embedded_vlc.py`. That
boundary is what lets us rebase against upstream Syncplay quarterly
without merge hell.

## Phase 1 — Scaffold and rip-out

Commit: `d45652e` Phase 1: scaffold syncplay-modern fork

- New git repo, with upstream Syncplay 1.7.5 imported as the initial
  commit (`0ff71cb`) so blame/history survives.
- `upstream` git remote added pointing at
  `https://github.com/Syncplay/syncplay.git` for future rebases.
- Apache 2.0 `LICENSE` preserved verbatim, `THIRD-PARTY-NOTICES.md`
  added listing dependency licenses (Syncplay Apache 2.0, PySide6 LGPL,
  Twisted MIT, python-vlc LGPL-2.1, libvlc LGPL-2.1, certifi MPL-2.0).
- Deleted player adapters that don't apply: `players/mpv.py`,
  `players/mpc.py`, `players/mpcbe.py`, `players/mplayer.py`,
  `players/iina.py`, `players/memento.py`, `players/mpvnet.py`,
  `players/vlc.py` (external-VLC adapter), and `ui/gui.py`,
  `ui/GuiConfiguration.py`.
- `pyproject.toml` added; Python pinned to `>=3.11` (python-vlc is
  brittle on 3.13+).
- `syncplay/constants.py`: `CONFIG_NAMES = [".syncplay-modern",
  "syncplay-modern.ini"]` so we don't collide with an upstream install
  on the same machine.

## Phase 2 — UI shell + chat + router + stub player

Commit: `713f471` Phase 2: working UI shell + stub player; protocol round-trip verified

This was the highest-leverage phase. The full UI contract was built
around a **stub player** so the protocol round-trip could be verified
before native-window risk was introduced.

- `syncplay/ui/modern/events.py`: Qt-free dataclasses (`ChatMessage`,
  `SyncEvent`, `ErrorEvent`, `ConnectionState`, `UserPresence`,
  `FileInfo`) and matching enums.
- `syncplay/ui/modern/messageRouter.py`: Qt-free classifier that
  implements every `UiManager`-targeted method (`showMessage`,
  `showChatMessage`, `showErrorMessage`, `userListChange`,
  `setControllerStatus`, etc.) and emits typed events. Unit-testable
  without `QApplication`. Sniffs connection-state substrings
  ("connection with server lost", "successfully connected") to drive
  the status-bar indicator.
- `syncplay/ui/modern/chatPanel.py`: chat bubbles for `ChatMessage`,
  subtle gray italic inline lines for `SyncEvent`, one-line
  `→ see Errors tab` pointer when an `ErrorEvent` arrives.
- `syncplay/ui/modern/errorsPanel.py`: persistent error log, separate
  tab, badge counter for unread errors, copyable.
- `syncplay/ui/modern/sidebarTabs.py`: tab bar (Chat / Errors) with
  badge.
- `syncplay/ui/modern/userStrip.py`: presence strip above the tabs.
- `syncplay/ui/modern/mainWindow.py`: `QMainWindow`, splitter, status
  bar with connection-state dot, full `UiManager` surface
  (`uiMode = constants.GRAPHICAL_UI_MODE`, `getUIMode()`, etc.).
- `syncplay/ui/modern/onboarding.py`: replaces upstream's
  `GuiConfiguration` — a single-screen first-run dialog defaulting to
  `syncplay.pl:8997`.
- `syncplay/players/embedded_vlc.py`: stub `BasePlayer` implementation
  with no-ops sufficient to satisfy `SyncplayClient.start()`. Class
  attrs: `speedSupported=True`, `chatOSDSupported=False`,
  `alertOSDSupported=False`.

**Verification:** two clients on the same host joined a room on
`syncplay.pl`, exchanged chat (rendered as bubbles), and observed each
other's sync events (rendered as gray inline lines). No video yet.

## Phase 3 — Embedded libvlc

Commit: `babbb77` Phase 3: embedded libvlc playback through the SyncplayClient surface

- `syncplay/players/embedded_vlc.py` replaced with the real adapter:
  - `vlc.Instance()` once at process start; `_get_instance()` falls
    back to a no-arg `vlc.Instance()` if the args form returns `None`
    (happens on some bundled libvlc builds).
  - Module-level registries (`set_video_widget()`,
    `set_fileinfo_sink()`) so the UI can hook in without threading
    state through many constructors.
  - `_ensure_vlc_plugin_path()` probes the standard system locations
    (`/usr/lib/x86_64-linux-gnu/vlc/plugins`, …) — needed for the
    PyInstaller bundle where libvlc can't find its own plugins.
  - `set_hwnd` / `set_xwindow` / `set_nsobject` branching by platform.
  - Position polling on a `QTimer` at `constants.PLAYER_ASK_DELAY`
    cadence; libvlc event callbacks (which fire on libvlc-internal
    threads) are marshaled back via `reactor.callFromThread(...)`
    before they touch the client or any Qt widget. **This rule is the
    most important invariant in the file — documented in the module
    docstring.**
  - Player helpers exposed for the keybindings layer: `toggle_pause`,
    `seek_by_seconds`, `set_volume`, `adjust_volume`, `toggle_mute`,
    `adjust_subtitle_delay_ms`, `adjust_audio_delay_ms`,
    `adjust_speed`, `reset_speed`.
- `syncplay/ui/modern/videoWidget.py`: `QWidget` with
  `Qt.WA_OpaquePaintEvent`, `Qt.WA_NativeWindow`,
  `Qt.WA_DontCreateNativeAncestors`, and an **empty `paintEvent`**.
  Without the empty `paintEvent`, Qt repaints over libvlc on every
  expose/resize. Drag-drop file handler. Keyboard focus enabled so the
  focus-aware shortcuts in Phase 5 work.
- `syncplay/ui/__init__.py`: forces `QT_QPA_PLATFORM=xcb` at startup
  when running under Wayland — libvlc can't draw into a Wayland
  surface in v1. This is set *before* `QApplication` is constructed.

**Verification:** two clients with the same local file in the same room
synchronise pause/play/seek across both. `slowOnDesync` smooths drift
via `setSpeed`. Resizing the window during playback repaints cleanly.

## Phase 4 — Settings panel

Commit: `72ec2de` Phase 4: settings dialog with live track switching and INI persistence

- `syncplay/ui/modern/settingsPanel.py` with `SettingsDialog`:
  - **Quick** section: audio track, subtitle track, subtitle delay,
    audio language, chat-on-video toggle, server/port/nickname/room.
  - **Advanced** collapsible section: every other Syncplay flag from
    `ConfigurationGetter._iniStructure`.
- Audio/subtitle dropdowns repopulate on the `MediaParsedChanged` libvlc
  event (tracks aren't available immediately on `openFile`).
- `syncplay/ui/ConfigurationGetter.py` gained four new keys in the
  `gui` section: `chatOnVideoEnabled` (default False),
  `layoutChatCollapsed`, `fullscreenAutohideMs`,
  `subtitleDelayDefaultMs`.
- Defaults tuned: `host=syncplay.pl`, `playerPath=__embedded_vlc__`,
  `forceGuiPrompt=False`, `showOSD*=False`.
- Removed the "if not file: force gui prompt" branch in
  `ConfigurationGetter` (this was breaking startup when no media file
  was passed).

## Phase 5 — Focus-aware keybindings

Commit: `31c1e11` Phase 5: focus-aware VLC-style keyboard shortcuts

- All shortcuts are `QShortcut` with `Qt.WidgetWithChildrenShortcut`
  context, attached to the video widget — **not** application-wide.
  This is the critical detail: `space` with chat focus types a space;
  `space` with video focus toggles pause.
- Bindings:
  - `f` toggle fullscreen, `Esc` exit fullscreen
  - `space` / `k` play/pause
  - `←` / `→` seek ±5s; `Shift+←/→` ±10s; `Ctrl+←/→` ±60s
  - `↑` / `↓` volume ±5%; `m` mute
  - `j` / `l` audio delay ±50ms
  - `g` / `h` subtitle delay ±50ms
  - `[` / `]` speed ±10%; `=` reset to 1.0×

## Phase 6 — Fullscreen + connection state

Commit: `f8207b7` Phase 6: fullscreen with auto-hide chat overlay + connection-state dot

- `mainWindow._fs_enter` / `_fs_exit`: collapse splitter, hide
  toolbars, `Qt.WindowFullScreen`.
- `_MouseEdgeFilter`: mouse within 40px of the right edge for >100ms
  reparents the chat panel into a translucent overlay at ~85% opacity.
- `_autohide_timer`: hides the overlay after `fullscreenAutohideMs`
  (default 3000ms) of inactivity.
- Status-bar connection dot: `MessageRouter` emits `ConnectionState`
  events on disconnect/reconnect by substring-matching upstream's
  error messages. The matcher catches both "connection with server
  lost, attempting to reconnect" and the success path.

## Phase 7 — Linux PyInstaller bundle

Commit: `683bad1` Phase 7: Linux PyInstaller bundle that actually runs

- `build/syncplay-modern.spec`: PyInstaller spec with hidden imports
  for Twisted internals (`twisted.internet.tcp`, etc.) and every
  `syncplay.messages_*` translation module. Pushes `repo_root` onto
  `sys.path` so the spec can introspect the package.
- `build/build-linux.sh`: wrapper that runs `uv venv` + `uv pip
  install -e . pyinstaller` + the spec.
- Bundle output: `dist/syncplay-modern/syncplay-modern` (~220 MB).
  Dynamically links libvlc from the user's system, so end-users still
  need VLC installed (`sudo apt install vlc`). `VLC_PLUGIN_PATH` is
  auto-detected from the standard system locations at startup via
  `_ensure_vlc_plugin_path()`.

## Phase 8 — CONTRIBUTING.md

Commit: `a0c66cc` Phase 8: CONTRIBUTING.md with upstream-rebase cadence and dev guide

- `CONTRIBUTING.md` documenting:
  - Development setup via `uv venv` + `uv pip install -e .`.
  - The repo layout and what's intended to stay upstream-compatible.
  - The **quarterly upstream rebase cadence**: `git fetch upstream;
    git rebase upstream/master`, drop the upstream UI/player files as
    conflict-deleted since we don't ship them.
  - Coding style, commit conventions (plain messages, no
    `Co-Authored-By` trailers), licensing.
  - Known-missing / wanted list (now broken out into
    [`02-roadmap.md`](02-roadmap.md)).

## Verified end-to-end

After Phase 8, the v0.1.0-alpha tag was cut. Verification at release:

- Two `syncplay-modern` instances joined room `efck-demo` on
  `syncplay.pl:8997`.
- Chat round-tripped in both directions (bubbles).
- Sync events from a peer rendered as gray italic inline lines.
- Pause/play/seek synchronised across both clients.
- `Esc`/`f` fullscreen, `space` pause-while-video-focused,
  `space`-types-a-space-while-chat-focused all worked.
- Disconnect → status dot red → Errors tab badge → Chat tab pointer
  `→ Connection lost · see Errors tab`. Reconnect → dot green.

The Linux PyInstaller bundle launches from `dist/syncplay-modern/` and
connects against a system libvlc.
