# Roadmap

Items deliberately deferred past v0.1.0-alpha. Order is rough priority,
not a commitment.

## Near-term (v0.2)

### Verified Windows / macOS bundles

The PyInstaller spec at `build/syncplay-modern.spec` is written to be
cross-platform — it doesn't shell out, it doesn't use Linux-only paths
in code (the libvlc plugin-path probe has macOS/Windows branches), and
the native-handle plumbing in `videoWidget.py` already has the
`set_hwnd` / `set_nsobject` cases. What's missing is **actually
running the build on those platforms** and fixing whatever breaks.

The likely points of friction:

- **Windows:** libvlc DLLs need to either be bundled into the spec
  (`binaries=` entry) or relied on at runtime from a system VLC
  install. The latter is the simpler choice — document the dependency.
- **macOS:** the upstream `buildPy2app.py` exists but hasn't been
  pointed at the new entry point. The `Qt.WA_NativeWindow` +
  `--vout=macosx` combination should work but needs to be verified on a
  Metal-layer machine.

### Pytest suite

Right now, behaviour is verified with one-off headless `QApplication`
scripts driven by `QtTest.QTest`. Each phase's commit message has a
"verification" block describing what was exercised. A proper `pytest`
suite — wrapping those scripts, adding coverage for the
`MessageRouter` classification (which is Qt-free and unit-testable) —
is a high-value contribution. Start with `MessageRouter`; that's the
component most likely to silently misclassify a future upstream
message-format change.

### In-video toast widget

Phase 4 added the `chatOnVideoEnabled` toggle, but the rendering half
is currently a no-op. With the flag on, we should render incoming chat
as a small, time-fading toast in a corner of the video — **not** as a
full VLC OSD overlay (we explicitly suppressed that). The toast should:

- Be non-modal and click-through.
- Fade out after ~4 seconds.
- Stack a few messages, oldest-first.
- Render through Qt (not libvlc), so it survives splitter resize and
  doesn't require any libvlc filter graph plumbing.

## Medium-term (v0.3)

### Playlist UI

Upstream Syncplay's playlist feature lives behind a config flag,
`sharedPlaylistEnabled`. We default it to `False` and don't expose any
UI for it. Bringing it back means:

- A second tab next to Chat / Errors (likely `Queue`), or a slide-out
  panel.
- The protocol surface for playlist ops is already in `client.py`;
  the `UiManager` methods (`addFileToPlaylist`, `setPlaylist`,
  `setPlaylistIndexFilename`) are already stubbed in `MessageRouter`,
  they just don't route anywhere visible.

### Wayland-native libvlc output

**Status:** deferred — see
[`docs/superpowers/specs/2026-05-17-wayland-libvlc-spike.md`](../docs/superpowers/specs/2026-05-17-wayland-libvlc-spike.md).

A 2026-05 investigation confirmed that libvlc 3.0.21 already ships the
relevant Wayland renderer modules (`wl_shm`, `wl_shell`, `egl_wl`,
`gl`, `glconv_vaapi_wl`). The blocker is python-vlc 3.x: it exposes
only `set_hwnd` / `set_xwindow` / `set_nsobject` for embedding, with
no `wl_surface` setter. The two viable today-paths are (A) `--vout=gl`
+ `QOpenGLWidget` with `video_set_callbacks` software readback — works
everywhere but burns VA-API acceleration; (B) wait for libvlc 4's
`libvlc_video_set_output_callbacks` to land in python-vlc — the
architecturally correct path, but blocked on external availability.
For now XWayland continues to work cleanly on every Wayland compositor
tested (Mutter, Plasma 6, Sway).

## Long-term / explicit non-goals for v1

These are documented in [`00-vision.md`](00-vision.md) as things this
fork is **not**. They are listed here only so contributors don't have to
re-derive the answer:

- **Auto-updates.** Out of scope.
- **Multi-player support.** No mpv/MPC/IINA/etc. The whole point of
  embedding libvlc was to delete the player-launch UX. We do not want
  to bring it back.
- **Mobile / web companions.** Out of scope. Use the official Syncplay
  upstream if you need that.
- **Custom theming / dark-mode toggle.** Inherit the OS theme via Qt.
- **New translations for new UI strings.** v1 ships English-only for
  the new shell strings; the existing 13 `messages_*.py` files are
  preserved for upstream-originated strings. Community translation PRs
  are welcome.
- **A "Syncplay-compatible" rebrand.** The name remains `syncplay-modern`
  (working) until a final name is picked. We do not use the "Syncplay"
  trademark in the product/domain per Apache 2.0 §6 courtesy.

## How to propose adding to this list

Open an issue. For anything touching the upstream-compatible files
(`client.py`, `protocols.py`, `constants.py`, `ConfigurationGetter.py`),
write up the design in `docs/superpowers/specs/` first. The cost of a
bad protocol-adjacent decision is a painful upstream rebase six months
from now.
