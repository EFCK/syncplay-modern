"""Light / Dark UI theme.

Provides:

- A small module-level state holder (current theme name).
- Two ready-to-apply Qt stylesheets keyed off the colour tables agreed
  for the project.
- Helpers the menu-bar toggle button uses for its label / tooltip.

Persistence is intentionally **not** done here. MainWindow reads the
saved value from the existing INI (via `ConfigurationGetter`'s `theme`
key under the `gui` section) and writes back through the same
`_persist_setting` path it uses for every other UI preference — that
keeps the on-disk config in one file instead of growing a parallel
JSON next to it.

Per-component widget stylesheets (the ready button's green, the chat
toggle's transparent chevron, the video controls' dark bar, etc.)
deliberately keep their own setStyleSheet calls and *override* this
global one, so their visual identity carries across themes.
"""

from __future__ import annotations

from typing import Literal


LIGHT = "light"
DARK = "dark"
Theme = Literal["light", "dark"]

DEFAULT: Theme = LIGHT


# ----------------------------------------------------------------------
# Stylesheets
# ----------------------------------------------------------------------

# Colour tables (from the agreed spec):
#
#   Element                       Light                          Dark
#   ----------------------------- ------------------------------ ------------------------------
#   Window / Widget bg            #f0f0f0                        #2b2b2b
#   Window / Widget text          #000000                        #e0e0e0
#   List / Edit / Combo bg        #ffffff                        #3c3f41
#   List / Edit / Combo border    #c0c0c0                        #555555
#   List item selected            #3399ff (text #ffffff)         #4b6eaf
#   List item hover               #e5e5e5                        #4a4a4a
#   Button bg / hover / pressed   #e0e0e0 / #d0d0d0 / #c0c0c0    #4a4a4a / #5a5a5a / #3a3a3a
#   ScrollBar track               #f0f0f0                        #3c3f41
#   ScrollBar handle / hover      #c0c0c0 / #a0a0a0              #5a5a5a / #6a6a6a
#   GraphicsView bg               #ffffff (border #c0c0c0)       #1e1e1e (border #555555)


_LIGHT_QSS = """
QWidget {
    background-color: #f0f0f0;
    color: #000000;
}
QMainWindow, QDialog { background-color: #f0f0f0; color: #000000; }

QMenuBar { background-color: #f0f0f0; color: #000000; }
QMenuBar::item { background: transparent; padding: 4px 8px; }
QMenuBar::item:selected { background-color: #e5e5e5; }
QMenu { background-color: #ffffff; color: #000000; border: 1px solid #c0c0c0; }
QMenu::item:selected { background-color: #3399ff; color: #ffffff; }

QStatusBar { background-color: #f0f0f0; color: #000000; }

QToolTip { background-color: #ffffff; color: #000000; border: 1px solid #c0c0c0; }

QListView, QListWidget, QTreeView, QTreeWidget, QTableView, QTableWidget,
QLineEdit, QTextEdit, QTextBrowser, QPlainTextEdit, QComboBox, QSpinBox,
QDoubleSpinBox, QAbstractSpinBox {
    background-color: #ffffff;
    color: #000000;
    border: 1px solid #c0c0c0;
    selection-background-color: #3399ff;
    selection-color: #ffffff;
}
QHeaderView::section {
    background-color: #f0f0f0;
    color: #000000;
    border: 1px solid #c0c0c0;
    padding: 4px;
}

QListView::item:hover, QListWidget::item:hover,
QTreeView::item:hover, QTableView::item:hover { background-color: #e5e5e5; }
QListView::item:selected, QListWidget::item:selected,
QTreeView::item:selected, QTableView::item:selected {
    background-color: #3399ff; color: #ffffff;
}

QPushButton {
    background-color: #e0e0e0;
    color: #000000;
    border: 1px solid #c0c0c0;
    padding: 4px 12px;
    border-radius: 3px;
}
QPushButton:hover { background-color: #d0d0d0; }
QPushButton:pressed { background-color: #c0c0c0; }
QPushButton:disabled { color: #888888; background-color: #ececec; }

QTabWidget::pane { border: 1px solid #c0c0c0; background-color: #f0f0f0; }
QTabBar::tab {
    background-color: #e0e0e0; color: #000000;
    padding: 5px 10px;
    border: 1px solid #c0c0c0;
}
QTabBar::tab:selected { background-color: #ffffff; }
QTabBar::tab:hover { background-color: #d0d0d0; }

QScrollBar:vertical, QScrollBar:horizontal { background: #f0f0f0; border: none; }
QScrollBar::handle:vertical, QScrollBar::handle:horizontal {
    background: #c0c0c0; border-radius: 3px; min-height: 24px; min-width: 24px;
}
QScrollBar::handle:vertical:hover, QScrollBar::handle:horizontal:hover {
    background: #a0a0a0;
}
QScrollBar::add-line, QScrollBar::sub-line { background: none; border: none; }
QScrollBar::add-page, QScrollBar::sub-page { background: none; }

QGraphicsView { background-color: #ffffff; border: 1px solid #c0c0c0; }

QCheckBox, QRadioButton, QGroupBox { color: #000000; }
QGroupBox { border: 1px solid #c0c0c0; margin-top: 8px; }
QGroupBox::title { subcontrol-origin: margin; left: 8px; padding: 0 4px; }
"""


_DARK_QSS = """
QWidget {
    background-color: #2b2b2b;
    color: #e0e0e0;
}
QMainWindow, QDialog { background-color: #2b2b2b; color: #e0e0e0; }

QMenuBar { background-color: #2b2b2b; color: #e0e0e0; }
QMenuBar::item { background: transparent; padding: 4px 8px; }
QMenuBar::item:selected { background-color: #4a4a4a; }
QMenu { background-color: #3c3f41; color: #e0e0e0; border: 1px solid #555555; }
QMenu::item:selected { background-color: #4b6eaf; color: #ffffff; }

QStatusBar { background-color: #2b2b2b; color: #e0e0e0; }

QToolTip { background-color: #3c3f41; color: #e0e0e0; border: 1px solid #555555; }

QListView, QListWidget, QTreeView, QTreeWidget, QTableView, QTableWidget,
QLineEdit, QTextEdit, QTextBrowser, QPlainTextEdit, QComboBox, QSpinBox,
QDoubleSpinBox, QAbstractSpinBox {
    background-color: #3c3f41;
    color: #e0e0e0;
    border: 1px solid #555555;
    selection-background-color: #4b6eaf;
    selection-color: #ffffff;
}
QHeaderView::section {
    background-color: #2b2b2b;
    color: #e0e0e0;
    border: 1px solid #555555;
    padding: 4px;
}

QListView::item:hover, QListWidget::item:hover,
QTreeView::item:hover, QTableView::item:hover { background-color: #4a4a4a; }
QListView::item:selected, QListWidget::item:selected,
QTreeView::item:selected, QTableView::item:selected {
    background-color: #4b6eaf; color: #ffffff;
}

QPushButton {
    background-color: #4a4a4a;
    color: #e0e0e0;
    border: 1px solid #555555;
    padding: 4px 12px;
    border-radius: 3px;
}
QPushButton:hover { background-color: #5a5a5a; }
QPushButton:pressed { background-color: #3a3a3a; }
QPushButton:disabled { color: #888888; background-color: #3a3a3a; }

QTabWidget::pane { border: 1px solid #555555; background-color: #2b2b2b; }
QTabBar::tab {
    background-color: #3c3f41; color: #e0e0e0;
    padding: 5px 10px;
    border: 1px solid #555555;
}
QTabBar::tab:selected { background-color: #4a4a4a; }
QTabBar::tab:hover { background-color: #4a4a4a; }

QScrollBar:vertical, QScrollBar:horizontal { background: #3c3f41; border: none; }
QScrollBar::handle:vertical, QScrollBar::handle:horizontal {
    background: #5a5a5a; border-radius: 3px; min-height: 24px; min-width: 24px;
}
QScrollBar::handle:vertical:hover, QScrollBar::handle:horizontal:hover {
    background: #6a6a6a;
}
QScrollBar::add-line, QScrollBar::sub-line { background: none; border: none; }
QScrollBar::add-page, QScrollBar::sub-page { background: none; }

QGraphicsView { background-color: #1e1e1e; border: 1px solid #555555; }

QCheckBox, QRadioButton, QGroupBox { color: #e0e0e0; }
QGroupBox { border: 1px solid #555555; margin-top: 8px; }
QGroupBox::title { subcontrol-origin: margin; left: 8px; padding: 0 4px; }
"""


# ----------------------------------------------------------------------
# Helpers
# ----------------------------------------------------------------------


def normalize(theme: str) -> Theme:
    return DARK if str(theme).strip().lower() == DARK else LIGHT


def stylesheet_for(theme: str) -> str:
    return _DARK_QSS if normalize(theme) == DARK else _LIGHT_QSS


def toggled(theme: str) -> Theme:
    return LIGHT if normalize(theme) == DARK else DARK


def button_label_for(theme: str) -> tuple[str, str]:
    """Return ``(text, tooltip)`` for a toggle button showing the
    *next* theme — i.e. if we're in light mode, we display a moon and
    "Switch to Dark theme"."""
    if normalize(theme) == DARK:
        return ("☀", "Switch to Light theme")
    return ("🌙", "Switch to Dark theme")


# ----------------------------------------------------------------------
# Component palette
# ----------------------------------------------------------------------
#
# Document-level CSS used by `QTextBrowser` widgets is *insertion-time*
# (Qt resolves it when HTML is appended to the document, not at paint
# time). To make the chat / errors / room log re-colour cleanly on a
# theme toggle, the panels regenerate their default stylesheets — and
# any inline-style spans they emit — from this palette and replay it
# through `setDefaultStyleSheet`.

_LIGHT_PALETTE = {
    # Chat panel
    "bubble-self": "#1d6fa5",   # blue, my messages
    "bubble-other": "#222222",  # near-black, peers
    "sysline": "#777777",       # gray italic system lines
    "errline": "#a13554",       # muted red for the see-Errors pointer
    "timestamp": "#888888",
    # Room panel labels + activity log
    "muted-label": "#555555",   # "Room:" header, "Activity" header
    "joined": "#1a8c5e",
    "left": "#888888",
    "ready": "#1a8c5e",
    "notready": "#a13554",
    "file": "#1d6fa5",
    "filename-empty": "#aaaaaa",  # "—" placeholder cell in user table
    # Errors panel
    "errors-category": "#555555",
    # Chat toggle button (transparent bg, sits over wrapper bg)
    "chat-toggle-fg": "#666666",
    "chat-toggle-hover-fg": "#000000",
    "chat-toggle-hover-bg": "rgba(0,0,0,30)",
    "chat-toggle-pressed-bg": "rgba(0,0,0,60)",
}

_DARK_PALETTE = {
    # Chat panel
    "bubble-self": "#6cb4e0",
    "bubble-other": "#eeeeee",
    "sysline": "#999999",
    "errline": "#e08090",
    "timestamp": "#888888",
    # Room panel labels + activity log
    "muted-label": "#aaaaaa",
    "joined": "#5ec896",
    "left": "#999999",
    "ready": "#5ec896",
    "notready": "#e08090",
    "file": "#6cb4e0",
    "filename-empty": "#666666",
    # Errors panel
    "errors-category": "#bbbbbb",
    # Chat toggle button
    "chat-toggle-fg": "#cfcfcf",
    "chat-toggle-hover-fg": "#ffffff",
    "chat-toggle-hover-bg": "rgba(255,255,255,38)",
    "chat-toggle-pressed-bg": "rgba(255,255,255,80)",
}


def palette(theme: str) -> dict:
    """Return the component-colour map for the given theme.

    Keys are stable across themes (see the dicts above); values are
    CSS-ready strings (`#rrggbb` or `rgba(…)`). Callers should look up
    keys rather than hard-coding hex values.
    """
    return _DARK_PALETTE if normalize(theme) == DARK else _LIGHT_PALETTE
