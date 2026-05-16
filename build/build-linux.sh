#!/usr/bin/env bash
# Build a Linux bundle of syncplay-modern using PyInstaller.
#
# Prerequisites:
#   - uv installed (https://docs.astral.sh/uv/)
#   - VLC installed on the build machine (libvlc.so.5 must be present)
#
# Output: dist/syncplay-modern/syncplay-modern
#
# The bundle does not include libvlc itself; users run-time linking it
# from their system VLC install. End-users must therefore have VLC
# installed (apt install vlc / dnf install vlc / equivalent).

set -euo pipefail

cd "$(dirname "$0")/.."

if [ ! -d .venv ]; then
    echo "Creating virtual environment with uv…"
    uv venv
fi

echo "Installing build dependencies…"
uv pip install -e . pyinstaller >/dev/null

echo "Building bundle…"
.venv/bin/pyinstaller --noconfirm build/syncplay-modern.spec

echo
echo "Built: dist/syncplay-modern/"
echo "Launch: ./dist/syncplay-modern/syncplay-modern"
echo
echo "Bundle size:"
du -sh dist/syncplay-modern
