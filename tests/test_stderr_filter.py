"""Tests for the stderr noise predicate.

The fd-level install path mutates the process's file descriptor 2,
which is impractical to exercise inside pytest without leaking state
between tests. We test the matching policy directly — the rest of
``install`` is plumbing around it.
"""

from __future__ import annotations

from syncplay.ui.stderr_filter import is_noise


def test_taglib_line_is_noise():
    """The libvlc / EBML demuxer's TagLib lines were the primary
    motivation for the filter — these must be dropped."""
    for line in (
        b"TagLib: Failed to find EBML head\n",
        b"TagLib: Failed to read VINT size\n",
        b"TagLib: Failed to parse EMBL ElementID\n",
        b"TagLib: Failed to read segment\n",
    ):
        assert is_noise(line), f"expected to drop: {line!r}"


def test_xdg_screensaver_line_is_noise():
    """``xset: command not found`` is emitted by xdg-screensaver as
    a subprocess; the line starts with the full xdg-screensaver
    path, not 'xset' directly."""
    line = b"/usr/bin/xdg-screensaver: line 670: xset: command not found\n"
    assert is_noise(line)


def test_leading_whitespace_does_not_disguise_noise():
    """Continuation lines (indented) from the same source still
    match. lstrip-then-prefix means a tab or spaces don't fool us."""
    assert is_noise(b"    TagLib: continuation\n")
    assert is_noise(b"\tTagLib: continuation\n")


def test_normal_libvlc_output_passes_through():
    """Real libvlc warnings (without the TagLib prefix) must NOT be
    dropped — losing those would hide actual problems."""
    samples = [
        b"[00007f0000000000] main libvlc warning: cannot open file\n",
        b"[syncplay-modern] Wayland session detected; forcing Qt to xcb...\n",
        b"Traceback (most recent call last):\n",
    ]
    for line in samples:
        assert not is_noise(line), f"expected to pass: {line!r}"


def test_empty_and_whitespace_lines_pass_through():
    """No content can't be noise. Pass empties through so we don't
    silently corrupt line counts in downstream tooling."""
    assert not is_noise(b"")
    assert not is_noise(b"\n")
    assert not is_noise(b"   \n")


def test_partial_taglib_substring_is_not_noise():
    """The filter is prefix-based by design — 'TagLib' must be at
    the start of the (lstripped) line. A line that merely mentions
    TagLib in the middle is real content and must pass."""
    line = b"warning: the TagLib library reported an issue\n"
    assert not is_noise(line)
