"""First-run connect dialog.

Exposes the contract `ConfigurationGetter` expects from a GUI config screen:
- class attribute `WindowClosed` (exception)
- `__init__(config, error=None)`
- `setAvailablePaths(paths)` (no-op; we only have one player)
- `run()` blocks until accepted or closed
- `getProcessedConfiguration()` returns a dict of updates
- `should_persist_dialog_fields()` returns True iff the user picked
  "Update Config and Run" (the caller uses this to decide whether to
  write the five dialog fields back to the INI).
"""

from __future__ import annotations

import os
import sys
from typing import Optional

from PySide6 import QtCore, QtGui, QtWidgets

from syncplay.ui.modern.i18n import tr


_DEFAULT_PORT = 8997


def _looks_like_vlc_dir(path: str) -> bool:
    """Best-effort: does this directory smell like a VLC install?

    Returns True if we can spot a libvlc binary or a sibling ``plugins``
    folder. False otherwise — we still save the path either way and let
    libvlc surface the real error at load time.
    """
    if not path or not os.path.isdir(path):
        return False
    try:
        entries = os.listdir(path)
    except OSError:
        return False
    for entry in entries:
        low = entry.lower()
        if low.startswith("libvlc") and (
            low.endswith(".dll")
            or low.endswith(".dylib")
            or low.endswith(".so")
            or ".so." in low
        ):
            return True
    if os.path.isdir(os.path.join(path, "plugins")):
        return True
    if sys.platform == "darwin" and os.path.isdir(
        os.path.join(path, "Contents", "MacOS")
    ):
        return True
    return False


def _coerce_password(raw) -> str:
    # INI stores "no password" as the literal string "None". Treat that
    # (and Python None) as empty so the dialog field doesn't show "None".
    if raw is None or raw == "None":
        return ""
    return str(raw)


class Onboarding(QtWidgets.QDialog):

    class WindowClosed(Exception):
        """Raised when the user closes the window instead of accepting."""

    def __init__(self, config: dict, error: Optional[str] = None) -> None:
        super().__init__()
        self._result: dict = {}
        self._accepted = False
        self._save_after_accept = False

        self.setWindowTitle(tr("connect-window-title"))
        self.setMinimumWidth(480)

        form = QtWidgets.QFormLayout()

        self._name_edit = QtWidgets.QLineEdit(config.get("name") or "")
        self._name_edit.setPlaceholderText(tr("onb-nickname-ph"))
        form.addRow(tr("onb-nickname"), self._name_edit)

        host_value = config.get("host") or "syncplay.pl"
        self._host_edit = QtWidgets.QLineEdit(host_value)
        form.addRow(tr("onb-server"), self._host_edit)

        self._port_combo = QtWidgets.QComboBox()
        self._port_combo.setEditable(True)
        self._port_combo.addItem(str(_DEFAULT_PORT))
        last_port = str(int(config.get("port") or _DEFAULT_PORT))
        if last_port != str(_DEFAULT_PORT):
            self._port_combo.insertItem(0, last_port)
        self._port_combo.setCurrentText(last_port)
        self._port_combo.setValidator(QtGui.QIntValidator(1, 65535, self))
        form.addRow(tr("onb-port"), self._port_combo)

        self._room_edit = QtWidgets.QLineEdit(config.get("room") or "")
        self._room_edit.setPlaceholderText(tr("onb-room-ph"))
        form.addRow(tr("onb-room"), self._room_edit)

        self._password_edit = QtWidgets.QLineEdit(_coerce_password(config.get("password")))
        self._password_edit.setEchoMode(QtWidgets.QLineEdit.Password)
        self._password_edit.setPlaceholderText(tr("onb-password-ph"))
        form.addRow(tr("onb-password"), self._password_edit)

        # VLC install location — auto-detected on most systems; the field
        # exists for people whose VLC is in a non-default location.
        self._vlc_path_edit = QtWidgets.QLineEdit(config.get("vlcInstallPath") or "")
        self._vlc_path_edit.setPlaceholderText(tr("onb-vlc-path-ph"))
        self._vlc_browse_btn = QtWidgets.QPushButton(tr("onb-browse"))
        self._vlc_browse_btn.clicked.connect(self._on_browse_vlc_path)
        vlc_row = QtWidgets.QHBoxLayout()
        vlc_row.addWidget(self._vlc_path_edit, 1)
        vlc_row.addWidget(self._vlc_browse_btn)
        form.addRow(tr("onb-vlc-path"), vlc_row)

        self._vlc_hint = QtWidgets.QLabel(tr("onb-vlc-hint-default"))
        self._vlc_hint.setStyleSheet("color:#888;")
        self._vlc_hint.setWordWrap(True)
        form.addRow("", self._vlc_hint)
        self._vlc_path_edit.editingFinished.connect(self._validate_vlc_path)
        self._validate_vlc_path()

        self._run_btn = QtWidgets.QPushButton(tr("onb-run"))
        self._run_btn.setToolTip(tr("onb-run-tip"))
        self._run_btn.clicked.connect(lambda: self._on_accept(persist=False))

        self._save_btn = QtWidgets.QPushButton(tr("onb-save-run"))
        self._save_btn.setToolTip(tr("onb-save-run-tip"))
        self._save_btn.setDefault(True)
        self._save_btn.setAutoDefault(True)
        self._save_btn.clicked.connect(lambda: self._on_accept(persist=True))

        button_row = QtWidgets.QHBoxLayout()
        button_row.addStretch(1)
        button_row.addWidget(self._run_btn)
        button_row.addWidget(self._save_btn)

        outer = QtWidgets.QVBoxLayout(self)
        if error:
            label = QtWidgets.QLabel(str(error))
            label.setStyleSheet("color:#c33;")
            label.setWordWrap(True)
            outer.addWidget(label)
        outer.addLayout(form)
        outer.addLayout(button_row)

    def setAvailablePaths(self, paths) -> None:  # noqa: N802 — keep upstream name
        return

    def _on_accept(self, persist: bool) -> None:
        name = self._name_edit.text().strip()
        host = self._host_edit.text().strip()
        room = self._room_edit.text().strip()
        port_text = self._port_combo.currentText().strip()
        if not name or not host or not room:
            QtWidgets.QMessageBox.warning(
                self,
                tr("onb-missing-title"),
                tr("onb-missing-body"),
            )
            return
        try:
            port = int(port_text)
        except ValueError:
            port = 0
        if not (1 <= port <= 65535):
            QtWidgets.QMessageBox.warning(
                self,
                tr("onb-bad-port-title"),
                tr("onb-bad-port-body"),
            )
            return
        self._result = {
            "name": name,
            "host": host,
            "port": port,
            "room": room,
            "password": self._password_edit.text(),
            "playerPath": "__embedded_vlc__",
            "vlcInstallPath": self._vlc_path_edit.text().strip(),
        }
        self._save_after_accept = persist
        self._accepted = True
        self.accept()

    def run(self) -> None:
        # `exec()` blocks until the dialog is closed.
        self.exec()
        if not self._accepted:
            raise Onboarding.WindowClosed()

    def getProcessedConfiguration(self) -> dict:  # noqa: N802 — keep upstream name
        return self._result

    def should_persist_dialog_fields(self) -> bool:
        return self._save_after_accept

    def _on_browse_vlc_path(self) -> None:
        start = self._vlc_path_edit.text().strip() or os.path.expanduser("~")
        folder = QtWidgets.QFileDialog.getExistingDirectory(
            self, "Select VLC installation folder", start
        )
        if folder:
            self._vlc_path_edit.setText(folder)
            self._validate_vlc_path()

    def _validate_vlc_path(self) -> None:
        path = self._vlc_path_edit.text().strip()
        if not path:
            self._vlc_hint.setStyleSheet("color:#888;")
            self._vlc_hint.setText(tr("onb-vlc-hint-default"))
            return
        if not os.path.isdir(path):
            self._vlc_hint.setStyleSheet("color:#c33;")
            self._vlc_hint.setText(tr("onb-vlc-hint-missing"))
            return
        if _looks_like_vlc_dir(path):
            self._vlc_hint.setStyleSheet("color:#888;")
            self._vlc_hint.setText(tr("onb-vlc-hint-ok"))
        else:
            self._vlc_hint.setStyleSheet("color:#c33;")
            self._vlc_hint.setText(tr("onb-vlc-hint-unknown"))
