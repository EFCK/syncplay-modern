# syncplay-modern (working name)

A modern, single-window desktop client for [Syncplay](https://syncplay.pl).
Built around an embedded libvlc player so video and chat live in the same
window, with a Teleparty-style layout: video on the left, a collapsible chat
panel on the right.

> **Status:** Early development. The protocol layer is feature-complete (it
> reuses upstream Syncplay's) but the UI is being rebuilt from scratch. Do
> not expect anything to work yet.

## Based on Syncplay

This project is a derivative of [Syncplay](https://github.com/Syncplay/syncplay),
licensed under the Apache License 2.0. It speaks the same network protocol,
so it connects to existing Syncplay servers (`syncplay.pl:8997` by default)
and is interoperable with the official Syncplay client. The sync algorithm
and core client logic are reused unchanged; the UI and player adapter are
replaced.

Please consider running [your own Syncplay server](https://github.com/Syncplay/syncplay#running-the-syncplay-server)
if your usage grows — the community servers are donated capacity.

## What's different from upstream Syncplay

- Single window: video and chat side by side; chat collapsible
- Embedded libvlc (no external VLC window)
- Tabbed sidebar: separate **Chat** and **Errors** tabs so error noise no
  longer drowns conversation
- Chat-on-video overlays off by default
- VLC-style keyboard shortcuts re-implemented inside the app, focus-aware
- Cleaner settings: language / audio / subtitle / subtitle delay in a Quick
  panel; everything else under collapsible Advanced

## Status / roadmap

See `docs/superpowers/specs/` for the design spec and implementation phases.

## Running from source

```bash
# Requires uv (https://docs.astral.sh/uv/) and VLC installed system-wide.
git clone https://github.com/<you>/syncplay-modern.git
cd syncplay-modern
uv venv
uv pip install -e .
.venv/bin/python syncplayClient.py --name <nick> --room <room>
```

End-users do not need VLC's GUI — only `libvlc.so.5` (Linux) /
`libvlc.dll` (Windows) / `libvlc.dylib` (macOS), which the standard VLC
install supplies.

## Building a distributable bundle

### Linux

```bash
./build/build-linux.sh
# → dist/syncplay-modern/syncplay-modern (~220 MB)
```

The bundle dynamically links libvlc from the user's system, so end-users
still need VLC installed (`sudo apt install vlc` on Debian/Ubuntu).
`VLC_PLUGIN_PATH` is auto-detected from the standard system locations at
startup.

### Windows / macOS

Upstream Syncplay ships `buildPy2exe.py` (Windows) and `buildPy2app.py`
(macOS); both are still present in this repo but have not been verified
against the new UI / player. The PyInstaller `.spec` at
`build/syncplay-modern.spec` is cross-platform and should produce a
working bundle on Windows or macOS too — copy the steps from
`build/build-linux.sh`, replacing the shell idioms. On those platforms
libvlc DLLs / dylibs must either be bundled (add them to the spec's
`binaries=` list) or rely on a system VLC install.

Contributions verifying Windows / macOS builds are welcome.

## License

Apache License 2.0. The original Syncplay copyright headers are preserved
on files we reuse. New files added in this fork carry their own copyright.
Third-party dependency licenses are listed in
[THIRD-PARTY-NOTICES.md](THIRD-PARTY-NOTICES.md).

## Credits

- **Upstream Syncplay** — protocol, sync algorithm, server, original client
  - Initial concept & core internals: Uriziel
  - GUI & long-time lead: Et0h
  - Original SyncPlay code: Tomasz Kowalczyk (Fluxid)
  - Full list: https://syncplay.pl/about/development/
- **This fork** — UI rewrite, libvlc embedding, refactored chat/error split:
  see `git log` for contributors.

## Trademarks

"Syncplay" is the upstream project's name. This fork is **not** an official
Syncplay product. The working codename here is `syncplay-modern`; final
naming will be decided closer to public release.
