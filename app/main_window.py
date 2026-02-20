"""
app/main_window.py – Main application window for ETS2 Light Sync.

Shows live log output, sync status, and provides Start/Stop/Settings controls.
Minimises to the system tray on close.
"""

import logging

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QCloseEvent, QFont
from PyQt6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QPlainTextEdit,
    QPushButton,
    QSizePolicy,
    QSystemTrayIcon,
    QVBoxLayout,
    QWidget,
)

from app.log_handler import QtLogHandler
from app.settings_dialog import SettingsDialog
from app.sync_worker import SyncWorker
from app.tray_icon import TrayIcon

_MAX_LOG_LINES = 500

log = logging.getLogger(__name__)


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("ETS2 Light Sync")
        self.setMinimumSize(640, 480)

        self._worker: SyncWorker | None = None

        self._build_ui()
        self._setup_logging()
        self._tray = TrayIcon(self, self)
        self._tray.show()

        log.info("ETS2 Light Sync ready — click Start to begin.")

    # ── UI construction ───────────────────────────────────────────────────────

    def _build_ui(self) -> None:
        central = QWidget()
        self.setCentralWidget(central)
        root = QVBoxLayout(central)
        root.setSpacing(8)
        root.setContentsMargins(10, 10, 10, 10)

        # ── Status row ────────────────────────────────────────────────────────
        self._status_label = QLabel("● Waiting for game   Game: --:--")
        self._status_label.setStyleSheet("font-weight: bold;")

        self._values_label = QLabel("Brightness: --   Color temp: --")

        status_layout = QVBoxLayout()
        status_layout.addWidget(self._status_label)
        status_layout.addWidget(self._values_label)
        root.addLayout(status_layout)

        # ── Button row ────────────────────────────────────────────────────────
        btn_layout = QHBoxLayout()

        self._start_btn = QPushButton("▶  Start")
        self._start_btn.clicked.connect(self.start_sync)

        self._stop_btn = QPushButton("■  Stop")
        self._stop_btn.clicked.connect(self.stop_sync)
        self._stop_btn.setEnabled(False)

        self._settings_btn = QPushButton("⚙  Settings")
        self._settings_btn.clicked.connect(self._open_settings)

        btn_layout.addWidget(self._start_btn)
        btn_layout.addWidget(self._stop_btn)
        btn_layout.addStretch()
        btn_layout.addWidget(self._settings_btn)
        root.addLayout(btn_layout)

        # ── Log area ──────────────────────────────────────────────────────────
        self._log_view = QPlainTextEdit()
        self._log_view.setReadOnly(True)
        mono = QFont("Consolas", 9)
        mono.setStyleHint(QFont.StyleHint.Monospace)
        self._log_view.setFont(mono)
        self._log_view.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding
        )
        root.addWidget(self._log_view)

    def _setup_logging(self) -> None:
        self._log_handler = QtLogHandler()
        self._log_handler.setLevel(logging.INFO)
        self._log_handler.log_emitted.connect(self._append_log)
        logging.getLogger().addHandler(self._log_handler)
        logging.getLogger().setLevel(logging.INFO)

    # ── Sync control ─────────────────────────────────────────────────────────

    def start_sync(self) -> None:
        if self._worker and self._worker.isRunning():
            return
        self._worker = SyncWorker()
        self._worker.status_changed.connect(self._on_status_changed)
        self._worker.light_updated.connect(self._on_light_updated)
        self._worker.finished.connect(self._on_worker_finished)
        self._worker.start()
        self._start_btn.setEnabled(False)
        self._stop_btn.setEnabled(True)
        self._tray.set_running(True)

    def stop_sync(self) -> None:
        if self._worker:
            self._worker.stop()
            # UI re-enable happens in _on_worker_finished

    # ── Signal handlers ───────────────────────────────────────────────────────

    def _on_status_changed(self, status: str) -> None:
        icons = {
            "running": "○",
            "connected": "●",
            "waiting": "○",
            "stopped": "■",
            "error": "✕",
        }
        icon = icons.get(status, "●")
        labels = {
            "running": "Running — waiting for game",
            "connected": "Game connected",
            "waiting": "Game disconnected",
            "stopped": "Stopped",
            "error": "Error — check settings",
        }
        text = labels.get(status, status)
        self._status_label.setText(f"{icon} {text}")

        if status in ("stopped", "error"):
            self._on_worker_finished()

    def _on_light_updated(self, game_time: int, brightness: int, kelvin: int) -> None:
        game_str = f"{game_time // 60:02d}:{game_time % 60:02d}"
        self._status_label.setText(f"● Game connected   Game: {game_str}")
        self._values_label.setText(
            f"Brightness: {brightness}/255   Color temp: {kelvin} K"
        )

    def _on_worker_finished(self) -> None:
        self._start_btn.setEnabled(True)
        self._stop_btn.setEnabled(False)
        self._tray.set_running(False)
        self._values_label.setText("Brightness: --   Color temp: --")

    def _append_log(self, msg: str) -> None:
        self._log_view.appendPlainText(msg)
        # Trim to max lines
        doc = self._log_view.document()
        while doc.blockCount() > _MAX_LOG_LINES:
            cursor = self._log_view.textCursor()
            cursor.movePosition(cursor.MoveOperation.Start)
            cursor.select(cursor.SelectionType.BlockUnderCursor)
            cursor.removeSelectedText()
            cursor.deleteChar()  # remove the trailing newline
        # Auto-scroll
        scrollbar = self._log_view.verticalScrollBar()
        scrollbar.setValue(scrollbar.maximum())

    def _open_settings(self) -> None:
        dlg = SettingsDialog(self)
        if dlg.exec() and self._worker and self._worker.isRunning():
            # Restart worker with new config
            self._worker.stop()
            self._worker.wait()
            self.start_sync()

    # ── Close → hide to tray ─────────────────────────────────────────────────

    def closeEvent(self, event: QCloseEvent) -> None:
        event.ignore()
        self.hide()
        self._tray.showMessage(
            "ETS2 Light Sync",
            "Still running in the system tray.",
            QSystemTrayIcon.MessageIcon.Information,
            2000,
        )
