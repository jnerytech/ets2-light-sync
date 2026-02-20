"""
app/tray_icon.py – System tray icon for ETS2 Light Sync.

Provides a context menu with Show/Hide, Start/Stop, and Quit actions.
Double-clicking the icon restores the main window.
"""

from PyQt6.QtCore import QSize
from PyQt6.QtGui import QColor, QIcon, QPainter, QPixmap
from PyQt6.QtWidgets import QApplication, QMenu, QSystemTrayIcon


def _make_icon(color: str = "#4CAF50") -> QIcon:
    """Generate a simple filled circle as the tray icon."""
    size = 64
    pixmap = QPixmap(QSize(size, size))
    pixmap.fill(QColor("transparent"))
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setBrush(QColor(color))
    painter.setPen(QColor("transparent"))
    painter.drawEllipse(4, 4, size - 8, size - 8)
    painter.end()
    return QIcon(pixmap)


class TrayIcon(QSystemTrayIcon):
    def __init__(self, window, parent=None) -> None:
        super().__init__(_make_icon(), parent)
        self._window = window
        self.setToolTip("ETS2 Light Sync")

        menu = QMenu()

        self._show_action = menu.addAction("Show Window")
        self._show_action.triggered.connect(self._show_window)

        menu.addSeparator()

        self._start_action = menu.addAction("Start")
        self._start_action.triggered.connect(window.start_sync)

        self._stop_action = menu.addAction("Stop")
        self._stop_action.triggered.connect(window.stop_sync)
        self._stop_action.setEnabled(False)

        menu.addSeparator()

        quit_action = menu.addAction("Quit")
        quit_action.triggered.connect(self._quit)

        self.setContextMenu(menu)
        self.activated.connect(self._on_activated)

    # ── Public ────────────────────────────────────────────────────────────────

    def set_running(self, running: bool) -> None:
        self._start_action.setEnabled(not running)
        self._stop_action.setEnabled(running)
        color = "#4CAF50" if running else "#9E9E9E"
        self.setIcon(_make_icon(color))

    # ── Private ───────────────────────────────────────────────────────────────

    def _show_window(self) -> None:
        self._window.show()
        self._window.raise_()
        self._window.activateWindow()

    def _on_activated(self, reason: QSystemTrayIcon.ActivationReason) -> None:
        if reason == QSystemTrayIcon.ActivationReason.DoubleClick:
            self._show_window()

    def _quit(self) -> None:
        self._window.stop_sync()
        QApplication.quit()
