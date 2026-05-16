"""First-run connect dialog.

Exposes the contract `ConfigurationGetter` expects from a GUI config screen:
- class attribute `WindowClosed` (exception)
- `__init__(config, error=None)`
- `setAvailablePaths(paths)` (no-op; we only have one player)
- `run()` blocks until accepted or closed
- `getProcessedConfiguration()` returns a dict of updates
"""

from __future__ import annotations

import sys
from typing import Optional

from PySide6 import QtCore, QtWidgets


class Onboarding(QtWidgets.QDialog):

    class WindowClosed(Exception):
        """Raised when the user closes the window instead of accepting."""

    def __init__(self, config: dict, error: Optional[str] = None) -> None:
        super().__init__()
        self._result: dict = {}
        self._accepted = False

        self.setWindowTitle("Connect to a Syncplay room")
        self.setMinimumWidth(380)

        form = QtWidgets.QFormLayout()

        self._name_edit = QtWidgets.QLineEdit(config.get("name") or "")
        self._name_edit.setPlaceholderText("Your nickname")
        form.addRow("Nickname", self._name_edit)

        host_value = config.get("host") or "syncplay.pl"
        self._host_edit = QtWidgets.QLineEdit(host_value)
        form.addRow("Server", self._host_edit)

        port_value = config.get("port") or 8997
        self._port_edit = QtWidgets.QSpinBox()
        self._port_edit.setRange(1, 65535)
        self._port_edit.setValue(int(port_value))
        form.addRow("Port", self._port_edit)

        self._room_edit = QtWidgets.QLineEdit(config.get("room") or "")
        self._room_edit.setPlaceholderText("Room name (any string)")
        form.addRow("Room", self._room_edit)

        self._password_edit = QtWidgets.QLineEdit(config.get("password") or "")
        self._password_edit.setEchoMode(QtWidgets.QLineEdit.Password)
        self._password_edit.setPlaceholderText("Optional")
        form.addRow("Server password", self._password_edit)

        button_box = QtWidgets.QDialogButtonBox(
            QtWidgets.QDialogButtonBox.Ok | QtWidgets.QDialogButtonBox.Cancel
        )
        button_box.accepted.connect(self._on_accept)
        button_box.rejected.connect(self.reject)

        outer = QtWidgets.QVBoxLayout(self)
        if error:
            label = QtWidgets.QLabel(str(error))
            label.setStyleSheet("color:#c33;")
            label.setWordWrap(True)
            outer.addWidget(label)
        outer.addLayout(form)
        outer.addWidget(button_box)

    def setAvailablePaths(self, paths) -> None:  # noqa: N802 — keep upstream name
        return

    def _on_accept(self) -> None:
        name = self._name_edit.text().strip()
        host = self._host_edit.text().strip()
        room = self._room_edit.text().strip()
        if not name or not host or not room:
            QtWidgets.QMessageBox.warning(
                self,
                "Missing fields",
                "Nickname, server, and room are all required.",
            )
            return
        self._result = {
            "name": name,
            "host": host,
            "port": int(self._port_edit.value()),
            "room": room,
            "password": self._password_edit.text(),
            "playerPath": "__embedded_vlc__",
        }
        self._accepted = True
        self.accept()

    def run(self) -> None:
        # `exec()` blocks until the dialog is closed.
        self.exec()
        if not self._accepted:
            raise Onboarding.WindowClosed()

    def getProcessedConfiguration(self) -> dict:  # noqa: N802 — keep upstream name
        return self._result
