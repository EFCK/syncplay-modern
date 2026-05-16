# Third-Party Notices

This file lists the third-party dependencies bundled or required by
`syncplay-modern`, along with their licenses and links.

## Forked from

| Project | License | Source |
|---|---|---|
| Syncplay (upstream) | Apache License 2.0 | https://github.com/Syncplay/syncplay |

The upstream Syncplay `LICENSE` is preserved verbatim in this repository.
Copyright headers on files reused unmodified are preserved.

## Runtime dependencies

| Library | License | Source |
|---|---|---|
| Python (CPython) | PSF-2.0 | https://www.python.org/ |
| PySide6 / Qt6 | LGPL-3.0 (Qt also commercial) | https://wiki.qt.io/Qt_for_Python |
| Twisted | MIT | https://twisted.org/ |
| python-vlc | LGPL-2.1+ | https://github.com/oaubert/python-vlc |
| libvlc (VLC core) | LGPL-2.1+ | https://www.videolan.org/vlc/ |
| qt5reactor (vendored) | MIT | https://github.com/sunu/qt5reactor |
| certifi | MPL-2.0 | https://github.com/certifi/python-certifi |
| pem | BSD-3-Clause | https://github.com/hynek/pem |
| zope.interface | ZPL-2.1 | https://github.com/zopefoundation/zope.interface |
| pypiwin32 (Windows only) | PSF | https://github.com/mhammond/pywin32 |
| appnope (macOS only) | BSD-2-Clause | https://github.com/minrk/appnope |
| requests (macOS only) | Apache-2.0 | https://requests.readthedocs.io |
| darkdetect (vendored) | BSD-3-Clause | https://github.com/albertosottile/darkdetect |

## LGPL compliance note

PySide6/Qt6, python-vlc, and libvlc are licensed under LGPL. Our distributed
binaries link to these libraries **dynamically** (Qt via PySide6's standard
distribution; libvlc via python-vlc's ctypes binding to the system or
bundled libvlc DLLs/dylibs). Per LGPL §6, this satisfies the relinking
requirement. The full LGPL text accompanies the libraries when bundled.

## Distribution caveat — community servers

The default server (`syncplay.pl:8997`) is community-donated infrastructure
maintained by the Syncplay project. Heavy users are encouraged to host their
own server (see upstream README).
