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

from typing import Optional

from PySide6 import QtCore, QtGui, QtWidgets


_DEFAULT_PORT = 8997


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

        self.setWindowTitle("Connect to a Syncplay room")
        self.setMinimumWidth(420)

        form = QtWidgets.QFormLayout()

        self._name_edit = QtWidgets.QLineEdit(config.get("name") or "")
        self._name_edit.setPlaceholderText("Your nickname")
        form.addRow("Nickname", self._name_edit)

        host_value = config.get("host") or "syncplay.pl"
        self._host_edit = QtWidgets.QLineEdit(host_value)
        form.addRow("Server", self._host_edit)

        self._port_combo = QtWidgets.QComboBox()
        self._port_combo.setEditable(True)
        self._port_combo.addItem(str(_DEFAULT_PORT))
        last_port = str(int(config.get("port") or _DEFAULT_PORT))
        if last_port != str(_DEFAULT_PORT):
            self._port_combo.insertItem(0, last_port)
        self._port_combo.setCurrentText(last_port)
        self._port_combo.setValidator(QtGui.QIntValidator(1, 65535, self))
        form.addRow("Port", self._port_combo)

        self._room_edit = QtWidgets.QLineEdit(config.get("room") or "")
        self._room_edit.setPlaceholderText("Room name (any string)")
        form.addRow("Room", self._room_edit)

        self._password_edit = QtWidgets.QLineEdit(_coerce_password(config.get("password")))
        self._password_edit.setEchoMode(QtWidgets.QLineEdit.Password)
        self._password_edit.setPlaceholderText("Optional")
        form.addRow("Server password", self._password_edit)

        self._run_btn = QtWidgets.QPushButton("Run")
        self._run_btn.setToolTip("Use these values for this session only; don't change the saved config.")
        self._run_btn.clicked.connect(lambda: self._on_accept(persist=False))

        self._save_btn = QtWidgets.QPushButton("Update Config and Run")
        self._save_btn.setToolTip("Save these values to the config and use them for this session.")
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
                "Missing fields",
                "Nickname, server, and room are all required.",
            )
            return
        try:
            port = int(port_text)
        except ValueError:
            port = 0
        if not (1 <= port <= 65535):
            QtWidgets.QMessageBox.warning(
                self,
                "Invalid port",
                "Port must be a number between 1 and 65535.",
            )
            return
        self._result = {
            "name": name,
            "host": host,
            "port": port,
            "room": room,
            "password": self._password_edit.text(),
            "playerPath": "__embedded_vlc__",
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
