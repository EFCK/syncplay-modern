# PyInstaller spec for syncplay-modern.
#
# Build:
#   cd <repo root>
#   .venv/bin/pyinstaller build/syncplay-modern.spec --noconfirm
#
# Output: dist/syncplay-modern/ (run dist/syncplay-modern/syncplay-modern).
#
# libvlc and its plugins are NOT bundled — they're loaded from the system
# at runtime via python-vlc. On Linux this means VLC must be installed
# (libvlc.so.5). On Windows / macOS the build scripts in the project root
# (buildPy2exe.py / buildPy2app.py) bundle libvlc DLLs / dylibs alongside
# the binary; users of this spec on Win/Mac should add those binaries
# manually under `binaries=` below if they want a self-contained build.

import os
import sys

block_cipher = None
repo_root = os.path.abspath(os.path.dirname(SPECPATH) if 'SPECPATH' in globals() else '.')
entry = os.path.join(repo_root, 'syncplayClient.py')

# Twisted has plenty of dynamically-imported submodules. PyInstaller's
# auto-detection misses a few that twisted[tls] / Conch use indirectly.
hidden_imports = [
    'twisted.internet.tcp',
    'twisted.internet.ssl',
    'twisted.protocols.tls',
    'twisted.internet.endpoints',
    'twisted.application.internet',
    'twisted.internet.protocol',
    'twisted.internet.defer',
    'twisted.internet.task',
    'twisted.internet.reactor',
    'twisted.python.versions',
    'zope.interface',
    'pem',
    'certifi',
    'vlc',
]

# Pull in our localized message modules — they're loaded by name from the
# `language` config and PyInstaller won't follow that string-based import.
# We have to push repo_root onto sys.path so we can import the package here
# inside the spec's clean namespace.
if repo_root not in sys.path:
    sys.path.insert(0, repo_root)
import pkgutil, syncplay
hidden_imports.extend(
    f'syncplay.{name}'
    for _, name, _ in pkgutil.iter_modules(syncplay.__path__)
    if name.startswith('messages_')
)

a = Analysis(
    [entry],
    pathex=[repo_root],
    binaries=[],
    datas=[
        # Bundle our resource files (icons, translations, etc.) so the
        # frozen app can find them next to the binary.
        (os.path.join(repo_root, 'syncplay', 'resources'),
         os.path.join('syncplay', 'resources')),
    ],
    hiddenimports=hidden_imports,
    hookspath=[],
    runtime_hooks=[],
    excludes=[
        # Drop the upstream players we don't use (already deleted on disk
        # but excluded defensively in case someone reintroduces them).
        'syncplay.players.mpv',
        'syncplay.players.mpc',
        'syncplay.players.mpcbe',
        'syncplay.players.mplayer',
        'syncplay.players.iina',
        'syncplay.players.ipc_iina',
        'syncplay.players.memento',
        'syncplay.players.mpvnet',
        'syncplay.players.vlc',
    ],
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='syncplay-modern',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,           # GUI mode — no console window on Windows
    disable_windowed_traceback=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name='syncplay-modern',
)
