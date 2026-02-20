"""
app/tray_icon.py – System tray icon for ETS2 Light Sync.

Provides a context menu with Show/Hide, Start/Stop, and Quit actions.
Double-clicking the icon restores the main window.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from PyQt6.QtGui import QAction
from PyQt6.QtWidgets import QApplication, QMenu, QSystemTrayIcon, QWidget

from app.icon import make_icon

if TYPE_CHECKING:
    from app.main_window import MainWindow


class TrayIcon(QSystemTrayIcon):
    def __init__(self, window: MainWindow, parent: QWidget | None = None) -> None:
        super().__init__(make_icon(indicator_color="#9E9E9E"), parent)
        self._window = window
        self.setToolTip("ETS2 Light Sync")

        menu = QMenu()

        show_action: QAction = menu.addAction("Show Window")  # type: ignore[assignment]
        show_action.triggered.connect(self._show_window)

        menu.addSeparator()

        self._start_action: QAction = menu.addAction("Start")  # type: ignore[assignment]
        self._start_action.triggered.connect(window.start_sync)

        self._stop_action: QAction = menu.addAction("Stop")  # type: ignore[assignment]
        self._stop_action.triggered.connect(window.stop_sync)
        self._stop_action.setEnabled(False)

        menu.addSeparator()

        quit_action: QAction = menu.addAction("Quit")  # type: ignore[assignment]
        quit_action.triggered.connect(self._quit)

        self.setContextMenu(menu)
        self.activated.connect(self._on_activated)

    # ── Public ────────────────────────────────────────────────────────────────

    def set_running(self, running: bool) -> None:
        self._start_action.setEnabled(not running)
        self._stop_action.setEnabled(running)
        color = "#4CAF50" if running else "#9E9E9E"
        self.setIcon(make_icon(indicator_color=color))

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
