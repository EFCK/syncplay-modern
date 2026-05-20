"""Drop known-noise lines from stderr without losing real output.

Two libvlc-adjacent sources flood the terminal on Linux:

- libvlc's matroska/EBML demuxer printing ``TagLib: Failed to ...``
  from C++ straight to fd 2. ``--quiet`` on the libvlc instance does
  not cover this — TagLib bypasses libvlc's logger and writes to the
  process's stderr directly.
- libvlc's screensaver inhibitor invoking ``xdg-screensaver`` which
  shells out to ``xset``. Minimal Wayland installs (Hyprland on
  CachyOS, etc.) often omit ``xset`` and the user sees
  ``/usr/bin/xdg-screensaver: line N: xset: command not found`` per
  load. README documents the install, but until that's done the
  spam swamps real output.

We splice a pipe in front of fd 2 and read each line in a daemon
thread; lines matching a known noise prefix are dropped, everything
else is forwarded to the original stderr. Installed only when stderr
is a TTY (interactive use) so pytest / CI captures stay untouched.
Set ``SYNCPLAY_NO_STDERR_FILTER=1`` to disable when debugging
libvlc itself.
"""

from __future__ import annotations

import os
import sys
import threading
from typing import Iterable


_NOISE_PREFIXES: tuple[bytes, ...] = (
    b"TagLib:",
    b"/usr/bin/xdg-screensaver",
)


def is_noise(line: bytes, prefixes: Iterable[bytes] = _NOISE_PREFIXES) -> bool:
    """True if `line` should be suppressed.

    Whitespace prefixes are tolerated so indented continuation
    lines from the same source still match. Split out from
    ``install`` so the matching policy is unit-testable without
    file-descriptor surgery.
    """
    stripped = line.lstrip()
    return any(stripped.startswith(p) for p in prefixes)


_installed = False


def install(prefixes: Iterable[bytes] = _NOISE_PREFIXES) -> bool:
    """Install the filter. Returns True on first call, False on
    subsequent calls or when conditions aren't right.

    Conditions to skip:
    - ``SYNCPLAY_NO_STDERR_FILTER`` set (debug escape hatch).
    - ``sys.stderr`` is not a TTY (captured by pytest / CI).
    - Already installed in this process.
    """
    global _installed
    if _installed:
        return False
    if os.environ.get("SYNCPLAY_NO_STDERR_FILTER"):
        return False
    try:
        if not sys.stderr.isatty():
            return False
    except (AttributeError, ValueError):
        # sys.stderr could be replaced with a non-stream object (e.g.
        # by pytest); treat as non-TTY and skip.
        return False

    try:
        read_fd, write_fd = os.pipe()
        saved_stderr_fd = os.dup(2)
        os.dup2(write_fd, 2)
        os.close(write_fd)
    except OSError:
        # If we can't dup, leave stderr alone — better noisy than broken.
        return False

    prefix_tuple = tuple(prefixes)

    def pump() -> None:
        try:
            with os.fdopen(read_fd, "rb", buffering=0) as src:
                while True:
                    line = src.readline()
                    if not line:
                        return
                    if is_noise(line, prefix_tuple):
                        continue
                    try:
                        os.write(saved_stderr_fd, line)
                    except OSError:
                        return
        except Exception:
            # The pump runs as a daemon; any exception here would
            # silently kill it and lose stderr. Swallow so the
            # process keeps running — worst case the user loses
            # filtering for a single line.
            pass

    thread = threading.Thread(target=pump, daemon=True, name="stderr-noise-filter")
    thread.start()
    _installed = True
    return True
