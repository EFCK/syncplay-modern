"""Tab strip cycling Room / Chat / Queue / Errors with unread badges.

Errors uses an inline "●N" text suffix on the tab label (cheap, no custom
painting). Chat uses a red rounded "+N" pill painted in the top-right
corner of the tab by `_BadgedTabBar.paintEvent` — it's the cue we want
for incoming peer chat messages while another tab is open. The pill
sits on top of the normal tab label without bumping the tab width and
clears when the user activates the Chat tab.
"""

from __future__ import annotations

from PySide6 import QtCore, QtGui, QtWidgets

from syncplay.ui.modern.i18n import tr


class _BadgedTabBar(QtWidgets.QTabBar):
    """QTabBar that paints small "+N" pills on top of selected tabs."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._counts: dict[int, int] = {}

    def set_badge_count(self, index: int, count: int) -> None:
        if count <= 0:
            self._counts.pop(index, None)
        else:
            self._counts[index] = count
        self.update()

    def paintEvent(self, event) -> None:
        super().paintEvent(event)
        if not self._counts:
            return
        painter = QtGui.QPainter(self)
        painter.setRenderHint(QtGui.QPainter.Antialiasing)
        font = painter.font()
        font.setBold(True)
        font.setPointSizeF(max(7.5, font.pointSizeF() - 1))
        painter.setFont(font)
        metrics = painter.fontMetrics()
        badge_h = metrics.height() + 2
        for index, count in self._counts.items():
            rect = self.tabRect(index)
            if not rect.isValid():
                continue
            text = f"+{count}"
            text_w = metrics.horizontalAdvance(text)
            badge_w = max(text_w + 8, badge_h)  # at least round
            x = rect.right() - badge_w - 4
            y = rect.top() + 2
            badge_rect = QtCore.QRectF(x, y, badge_w, badge_h)
            painter.setPen(QtCore.Qt.NoPen)
            painter.setBrush(QtGui.QColor(220, 53, 53))
            painter.drawRoundedRect(badge_rect, badge_h / 2, badge_h / 2)
            painter.setPen(QtCore.Qt.white)
            painter.drawText(badge_rect, QtCore.Qt.AlignCenter, text)
        painter.end()


class SidebarTabs(QtWidgets.QTabWidget):

    ROOM_INDEX = 0
    CHAT_INDEX = 1
    QUEUE_INDEX = 2
    ERRORS_INDEX = 3

    def __init__(
        self,
        room_panel: QtWidgets.QWidget,
        chat_panel: QtWidgets.QWidget,
        queue_panel: QtWidgets.QWidget,
        errors_panel: QtWidgets.QWidget,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self._unread = 0
        self._chat_unread = 0
        self._badge_bar = _BadgedTabBar(self)
        self.setTabBar(self._badge_bar)
        self.addTab(room_panel, tr("tab-room"))
        self.addTab(chat_panel, tr("tab-chat"))
        self.addTab(queue_panel, tr("tab-queue"))
        self.addTab(errors_panel, tr("tab-errors"))
        self.currentChanged.connect(self._on_changed)
        self._refresh_errors_label()

    def note_error(self) -> None:
        if self.currentIndex() == self.ERRORS_INDEX:
            return
        self._unread += 1
        self._refresh_errors_label()

    def reset_unread(self) -> None:
        self._unread = 0
        self._refresh_errors_label()

    def note_chat(self) -> None:
        """Bump the unread chat count; surfaces as a red "+N" pill on
        the Chat tab. No-op while Chat is already the current tab.
        """
        if self.currentIndex() == self.CHAT_INDEX:
            return
        self._chat_unread += 1
        self._badge_bar.set_badge_count(self.CHAT_INDEX, self._chat_unread)

    def reset_chat_unread(self) -> None:
        self._chat_unread = 0
        self._badge_bar.set_badge_count(self.CHAT_INDEX, 0)

    def chat_unread_count(self) -> int:
        return self._chat_unread

    def _on_changed(self, index: int) -> None:
        if index == self.ERRORS_INDEX:
            self.reset_unread()
        if index == self.CHAT_INDEX:
            self.reset_chat_unread()

    def _refresh_errors_label(self) -> None:
        base = tr("tab-errors")
        if self._unread:
            self.setTabText(self.ERRORS_INDEX, f"{base} ●{self._unread}")
        else:
            self.setTabText(self.ERRORS_INDEX, base)

    def retranslate(self) -> None:
        self.setTabText(self.ROOM_INDEX, tr("tab-room"))
        self.setTabText(self.CHAT_INDEX, tr("tab-chat"))
        self.setTabText(self.QUEUE_INDEX, tr("tab-queue"))
        # Errors keeps its unread-count suffix; the helper covers both.
        self._refresh_errors_label()
