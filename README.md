# syncplay-modern (working name)

A modern, single-window desktop client for [Syncplay](https://syncplay.pl).
Built around an embedded libvlc player so video and chat live in the same
window, with a Teleparty-style layout: video on the left, a collapsible chat
panel on the right.

> **Status:** v0.1.0-alpha plus an in-progress v0.2 cycle (in-video toasts,
> shared playlist UI, pytest suite, Windows builds via GitHub Actions).
> The protocol layer is reused unchanged from upstream Syncplay; the GUI
> and player adapter have been replaced. Linux is the primary development
> target. Windows zips are produced by CI and available from Releases;
> macOS users currently run from source.

## Aim of this project

Syncplay's protocol, sync algorithm, and server ecosystem (`syncplay.pl`) are
excellent and have been stable for years. The user experience has not aged as
well: chat lives in a separate window from the video, system events and
user chat are jumbled together in a single text stream, errors interrupt
conversation in red, and notifications overlay onto the video by default.

`syncplay-modern` keeps everything that already works — the network protocol,
the desync correction, the room/identity model, the existing community
servers — and **replaces only the surface**. The goals, in order:

1. **Stay protocol-compatible.** A `syncplay-modern` user joining a room
   alongside upstream Syncplay users must Just Work. No new servers, no new
   accounts, no fragmentation of the community.
2. **One window, like Teleparty.** Video on the left, chat on the right,
   chat collapsible. No second VLC window to alt-tab to.
3. **Separate chat from noise.** Sync events (paused/seeked/joined) are
   small gray inline lines in the Chat tab. Errors live in their own Errors
   tab with a badge counter. Chat is for chat.
4. **Sensible defaults.** Chat-on-video overlays off by default. OSD
   notifications off by default. The settings panel surfaces the four
   things people actually change (audio track, subtitle track, subtitle
   delay, language); everything else is in collapsible Advanced.
5. **VLC keyboard muscle memory.** `f` fullscreen, `space` pause, arrows
   seek, `j/l` audio delay, `g/h` subtitle delay, `[/]` speed — all
   focus-aware so they don't fire while you're typing in chat.
6. **Cross-platform desktop app**, distributable as a single bundle on
   Linux/Windows/macOS.

See [`plans/`](plans/) for the design document, the record of initial
changes, and what's planned next.

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

## How to run

### Prerequisites

- **VLC installed system-wide.** The app links against the system's
  libvlc at runtime. You don't need the VLC GUI, only the library:
  - Linux: `sudo apt install vlc` (Debian/Ubuntu) or equivalent
  - Windows: install VLC from https://www.videolan.org/
  - macOS: install VLC from https://www.videolan.org/ or `brew install
    --cask vlc`
- **Python 3.11 or 3.12.** `python-vlc` is brittle on 3.13+, and the
  `pyproject.toml` pins `>=3.11`. 3.12 is the recommended version.
- **`uv`** for environment management: see
  https://docs.astral.sh/uv/getting-started/installation/
- **Linux only:** on Wayland you also need `libxcb-cursor0` because the
  app forces the xcb Qt platform plugin (libvlc can't draw into a
  Wayland surface in v1):
  `sudo apt install libxcb-cursor0`

### Run from source

```bash
git clone https://github.com/EFCK/syncplay-modern.git
cd syncplay-modern
uv sync                          # creates .venv and installs deps
uv run syncplayClient.py
```

On first run, an onboarding dialog asks for nickname, room, and server
(defaults to `syncplay.pl:8997`). Subsequent runs read the saved INI
and go straight to the main window.

To skip onboarding and pass everything on the command line:

```bash
uv run syncplayClient.py --name alice --room movie-night
```

### Open a video

You can:

- Drag and drop a video file onto the video panel.
- Use **File → Open File…** in the menu bar.
- Upstream's `--player-path` argument is ignored; the embedded libvlc
  player is selected automatically.

### Keyboard shortcuts

These are focus-aware — they fire when the video widget has focus, not
when you're typing in chat. Click on the video (or press Tab to focus
it) to activate them.

| Key                | Action                          |
|--------------------|---------------------------------|
| `f`                | Toggle fullscreen               |
| `Esc`              | Exit fullscreen                 |
| `space` / `k`      | Play / pause                    |
| `←` / `→`          | Seek ±5 seconds                 |
| `Shift+←` / `→`    | Seek ±10 seconds                |
| `Ctrl+←` / `→`     | Seek ±60 seconds                |
| `↑` / `↓`          | Volume ±5%                      |
| `m`                | Mute toggle                     |
| `j` / `l`          | Audio delay ±50 ms              |
| `g` / `h`          | Subtitle delay ±50 ms           |
| `b`                | Cycle to next audio track       |
| `v`                | Cycle to next subtitle track    |
| `[` / `]`          | Playback speed ±10%             |
| `=`                | Reset speed to 1.0×             |

### Run the prebuilt Linux bundle

If you don't want a Python environment on the host, build the bundle
once (see [Building a distributable bundle](#building-a-distributable-bundle))
and run it directly:

```bash
./build/build-linux.sh                          # one-time, ~2 min
./dist/syncplay-modern/syncplay-modern
```

The bundle still needs VLC installed on the host (it links libvlc
dynamically) but doesn't need Python or `uv`.

### Run on Windows (prebuilt)

1. Install **64-bit VLC for Windows** from <https://www.videolan.org/>.
   The app loads `libvlc.dll` from the system VLC at runtime — you don't
   need to launch VLC itself, but the install supplies the DLLs.
2. Download the latest `syncplay-modern-vX.Y.Z-windows.zip` from the
   [Releases page](https://github.com/EFCK/syncplay-modern/releases). If
   no Release is up yet, the most recent CI build is downloadable from
   the **Actions** tab → most recent green run → **Artifacts**.
3. Unzip anywhere. The build is portable — no installer, no registry
   entries.
4. Double-click `syncplay-modern.exe` inside the unzipped folder.
5. On first launch, Windows SmartScreen may show "Windows protected your
   PC" because the binary is unsigned. Click **More info** → **Run
   anyway**. The prompt is cached per binary; subsequent launches don't
   show it.
6. Fill in the connect dialog: nickname, server (`syncplay.pl`), port
   (`8997`), and any room name. Leave **VLC location** blank if VLC is
   in `C:\Program Files\VideoLAN\VLC`. If you installed VLC somewhere
   else (portable install, different drive), click **Browse** and pick
   the folder containing `libvlc.dll`.
7. Click **Update Config and Run** to save the settings to
   `%APPDATA%\Syncplay\` and use them this session, or **Run** to use
   them for this session only without persisting.

The Windows .exe is x64. You need 64-bit VLC; the 32-bit installer
won't work.

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

### Windows

Windows zips are built by GitHub Actions on every `v*` tag push and on
manual workflow dispatch — see `.github/workflows/build-windows.yml`.
The workflow runs `pyinstaller build/syncplay-modern.spec` on a
`windows-latest` runner, zips `dist/syncplay-modern/`, and attaches the
result to the GitHub Release for tagged builds.

To build locally on Windows (requires Python 3.12, uv, and VLC):

```pwsh
uv venv
uv pip install -e .
uv pip install pyinstaller
uv run pyinstaller --noconfirm build/syncplay-modern.spec
# → dist/syncplay-modern/syncplay-modern.exe
```

libvlc is **not** bundled — the .exe links against the user's system
VLC install via `libvlc.dll`. The "VLC location" field in the
onboarding dialog lets users point at non-default VLC install paths.

### macOS

No CI workflow yet. The PyInstaller spec at `build/syncplay-modern.spec`
is cross-platform and should produce a working `.app` on macOS, but
this has not been verified. The legacy `buildPy2app.py` in the repo
root is upstream's py2app driver and is unmaintained for this fork.
For now, macOS users run from source via `uv run syncplayClient.py`.
Contributions verifying a macOS build are welcome.

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
