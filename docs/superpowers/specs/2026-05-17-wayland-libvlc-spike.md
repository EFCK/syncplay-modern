# Wayland-native libvlc output — investigation spike

**Date:** 2026-05-17
**Status:** investigation only — no production code changed
**Tracks roadmap item:** `plans/02-roadmap.md` → "Wayland-native libvlc output"

## TL;DR

The libvlc on the dev machine (VLC 3.0.21) **already has** native Wayland
video-output modules built in: `wl_shm`, `wl_shell`, `egl_wl`, and the
GL-based `gl` / `glconv_vaapi_wl`. The blocker is not at the VLC layer;
it is at the **embedding boundary** between Qt and python-vlc.
python-vlc 3.x exposes three platform window handle setters
(`set_hwnd`, `set_xwindow`, `set_nsobject`) and nothing equivalent for a
`wl_surface`. The "newer" callback-based API in libvlc 4 that would solve
this cleanly is not yet released.

There are two viable paths to native Wayland output today; both are
non-trivial enough that they should not be undertaken inside this roadmap
slice. XWayland continues to work and stays the default for v0.2/v0.3.

## What the current code does

`syncplay/ui/__init__.py:9-10` forces XWayland whenever the session is
Wayland:

```python
if os.environ.get("XDG_SESSION_TYPE") == "wayland":
    os.environ.setdefault("QT_QPA_PLATFORM", "xcb")
```

`syncplay/players/videoWidget.py:82-90` then unconditionally calls
`media_player.set_xwindow(int(self.winId()))` on Linux. Under XWayland
that `winId()` is an X11 window resource and libvlc draws into it via
the `xcb` / `xcb_xv` modules.

## Observations from libvlc 3.0.21 on this machine

```
$ vlc --list | grep -i wayland
  egl_wl                 EGL extension for OpenGL
  glconv_vaapi_wl        VA-API OpenGL surface converter for Wayland
  wl_shm                 Wayland shared memory video output
  wl_shell               Wayland shell surface
```

So the renderers are there. What's missing is a way to tell libvlc
"render into *this* `wl_surface*`" — the C API does not expose such a
setter in libvlc 3.x.

## Path A — `--vout=gl` + `QOpenGLWidget` with callback render

Set `--vout=gl` on the libvlc instance and use
`libvlc_video_set_callbacks(lock, unlock, display, opaque)` to receive
decoded frames in a memory buffer, then upload them as a texture into a
`QOpenGLWidget`. The OpenGL widget is platform-agnostic and renders the
texture through the Qt scene graph — Qt handles the wl_surface
negotiation itself.

**Pros:** survives Wayland *and* X11 without conditional code, gives the
overlay composing for free (Qt widgets stack naturally on top of the
GL widget, so the `VideoControls` bar and the fullscreen chat overlay
become trivial again — no more "child of WA_NativeWindow gets painted
over" workarounds), and the libvlc thread → Qt main thread marshaling
is already in place via `reactor.callFromThread` for the player-state
hooks.

**Cons:**
1. Decoded frames are copied through CPU memory (`set_callbacks` is the
   software path), so 4K @ 60 fps would saturate one core just on the
   blit. The 1080p use case is probably fine but is unverified.
2. Hardware acceleration (VA-API) bypasses this path — frames go
   through DRM/EGL natively, but `set_callbacks` forces a readback. We
   would lose ~10-15W of GPU acceleration per stream.
3. Color-space and pixel-format wrangling
   (`libvlc_video_set_format_callbacks`) is fiddly — yuv420p → RGB
   conversion in the shader, NV12 too, plus chroma siting and BT.601
   vs. BT.709 selection. Not hard, but tedious.

**Effort estimate:** 3–4 focused days for a working prototype, another
2–3 for matching feature parity with `set_xwindow` (subtitle render
position, OSD suppression, hardware-decoded frame handoff if
salvageable).

## Path B — wait for libvlc 4 + `libvlc_video_set_output_callbacks`

libvlc 4 ships `libvlc_video_set_output_callbacks` which lets the host
supply an EGL/OpenGL context plus framebuffer setup; libvlc renders
directly into the host's GL context using its own decode pipeline (VA-API
preserved). This is what mpv does today and is the correct long-term
answer.

**Pros:** no CPU readback, hardware acceleration preserved, single
code path for Wayland/X11/Windows/macOS, no Qt vs. native-handle
wrangling.

**Cons:** libvlc 4 has been "soon" for years. As of 2026-05 it remains
in unstable. python-vlc binds against the installed libvlc at runtime,
so we would need to either bundle libvlc 4 ourselves (large) or wait
for distros to ship it (slow). Two issues compound this: hardware
acceleration interactions with Wayland compositors on libvlc 4 are not
yet documented well, and python-vlc has not yet exposed the new
output-callbacks setter.

**Effort estimate:** mostly waiting; ~1 day of integration work once
libvlc 4 is broadly available.

## Why this isn't shipping in this slice

The roadmap entry tagged this work investigative ("neither path is
well-trodden"). After this spike:

- Path A is technically achievable today, but burns the v0.3 budget on
  one feature and arrives with an unhappy hardware-accel regression.
- Path B is the architecturally correct choice but blocked on
  external availability.

The current XWayland behavior produces correct output on every Wayland
compositor we have tested (GNOME 46/Mutter, KDE Plasma 6, Sway). The
only user-visible cost is the XWayland subsystem itself, which most
distros run by default for compatibility regardless.

## Recommendation

1. **Keep the xcb force in place.** It is one line in
   `syncplay/ui/__init__.py` and is the smallest correctness fix
   shipping today.
2. **Defer the native path to the libvlc 4 timeline.** Track the
   python-vlc and libvlc-4 release status; reopen this spec when
   `libvlc_video_set_output_callbacks` is callable from python-vlc.
3. **Optional follow-up (separate, opt-in):** prototype Path A behind
   an environment variable (`SYNCPLAY_GL_VOUT=1`) so power users on
   pure Wayland with discrete GPUs can opt in. Do not make it the
   default. This is not on the v0.3 critical path.

## What changes on `master` from this spike

Nothing. The spec lands; `master` behavior is unchanged. `plans/02-roadmap.md`
gets a one-paragraph update pointing at this spec and reflecting
"deferred pending libvlc 4 / python-vlc".

## References

- `syncplay/ui/__init__.py:9-10` — current xcb force.
- `syncplay/players/videoWidget.py:82-90` — current `set_xwindow` call.
- `syncplay/players/embedded_vlc.py:95-107` — current `vlc.Instance` args.
- python-vlc surface APIs: `set_xwindow` (line 3196), `set_hwnd`,
  `set_nsobject`, `video_set_callbacks` (line 3439), `video_set_format`
  (no `wl_surface` equivalent).
- libvlc module inventory on this dev box: VLC 3.0.21 ships
  `wl_shm`/`wl_shell`/`egl_wl`/`gl`/`glconv_vaapi_wl`.
