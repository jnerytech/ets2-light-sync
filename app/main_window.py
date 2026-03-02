"""
app/main_window.py – Main application window for ETS2 Light Sync.

Shows live log output, sync status, and provides Start/Stop/Settings controls.
Minimises to the system tray on close.
"""

import io
import logging

from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QCloseEvent, QFont, QPixmap
from PyQt6.QtWidgets import (
    QApplication,
    QComboBox,
    QDialog,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QPlainTextEdit,
    QPushButton,
    QSizePolicy,
    QSystemTrayIcon,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from app import config, theme
from app.icon import make_icon
from app.log_handler import QtLogHandler
from app.map_widget import MapPanel
from app.settings_dialog import SettingsDialog
from app.state import AppState
from app.sync_worker import SyncWorker
from app.tray_icon import TrayIcon
from app.web_server import WebServer

_MAX_LOG_LINES = 500

log = logging.getLogger(__name__)


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("ETS2 Light Sync")
        self.setMinimumSize(700, 520)

        self._worker: SyncWorker | None = None

        # ── Shared state + web server ─────────────────────────────────────────
        self._state = AppState()
        self._web = WebServer(self._state)
        self._web.start()

        self._build_ui()
        self._setup_logging()
        self._tray = TrayIcon(self, self)
        self._tray.show()

        # QTimer drains pending start/stop actions queued by the web server.
        self._action_timer = QTimer(self)
        self._action_timer.timeout.connect(self._drain_pending_actions)
        self._action_timer.start(500)

        log.info("ETS2 Light Sync ready — click Start to begin.")

    # ── UI construction ───────────────────────────────────────────────────────

    def _build_ui(self) -> None:
        central = QWidget()
        self.setCentralWidget(central)
        root = QVBoxLayout(central)
        root.setSpacing(4)
        root.setContentsMargins(8, 8, 8, 8)

        # ── Button row ────────────────────────────────────────────────────────
        btn_layout = QHBoxLayout()

        self._start_btn = QPushButton("▶  Start")
        self._start_btn.clicked.connect(self.start_sync)

        self._stop_btn = QPushButton("■  Stop")
        self._stop_btn.clicked.connect(self.stop_sync)
        self._stop_btn.setEnabled(False)

        self._settings_btn = QPushButton("⚙  Settings")
        self._settings_btn.clicked.connect(self._open_settings)

        copy_btn = QPushButton("⎘  Copy Logs")
        copy_btn.clicked.connect(self._copy_logs)

        web_btn = QPushButton("📱  Web")
        web_btn.setToolTip("Abrir dashboard no celular via QR Code")
        web_btn.clicked.connect(self._show_web_dialog)

        self._theme_combo = QComboBox()
        self._theme_combo.addItems(theme.THEMES)
        saved_theme = config.load().get("theme", "System")
        self._theme_combo.setCurrentText(saved_theme)
        self._theme_combo.currentTextChanged.connect(self._on_theme_changed)  # type: ignore[misc]

        btn_layout.addWidget(self._start_btn)
        btn_layout.addWidget(self._stop_btn)
        btn_layout.addStretch()
        btn_layout.addWidget(copy_btn)
        btn_layout.addWidget(web_btn)
        btn_layout.addWidget(self._settings_btn)
        btn_layout.addWidget(self._theme_combo)
        root.addLayout(btn_layout)

        # ── Tab widget ────────────────────────────────────────────────────────
        tabs = QTabWidget()

        # Tab 1: Sync status + log
        sync_tab = QWidget()
        sync_layout = QVBoxLayout(sync_tab)
        sync_layout.setSpacing(6)
        sync_layout.setContentsMargins(0, 6, 0, 0)

        self._status_label = QLabel("● Waiting for game   Game: --:--")
        self._status_label.setStyleSheet("font-weight: bold;")
        self._values_label = QLabel("Brightness: --   Color temp: --")
        self._tz_label     = QLabel("Timezone: --")
        self._country_label = QLabel("Country: --")

        sync_layout.addWidget(self._status_label)
        sync_layout.addWidget(self._values_label)
        sync_layout.addWidget(self._tz_label)
        sync_layout.addWidget(self._country_label)

        self._log_view = QPlainTextEdit()
        self._log_view.setReadOnly(True)
        mono = QFont("Consolas", 9)
        mono.setStyleHint(QFont.StyleHint.Monospace)
        self._log_view.setFont(mono)
        self._log_view.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding
        )
        sync_layout.addWidget(self._log_view)

        tabs.addTab(sync_tab, "Sync")

        # Tab 2: Map + simulation
        self._map_panel = MapPanel()
        tabs.addTab(self._map_panel, "Map")

        root.addWidget(tabs)

    def _setup_logging(self) -> None:
        self._log_handler = QtLogHandler()
        self._log_handler.setLevel(logging.INFO)
        self._log_handler.log_emitted.connect(self._append_log)
        logging.getLogger().addHandler(self._log_handler)
        logging.getLogger().setLevel(logging.INFO)

        # Mirror log lines into the shared state so the web dashboard shows them.
        state_handler = _StateLogHandler(self._state)
        state_handler.setLevel(logging.INFO)
        logging.getLogger().addHandler(state_handler)

    # ── Sync control ─────────────────────────────────────────────────────────

    def start_sync(self) -> None:
        if self._worker and self._worker.isRunning():
            return
        self._worker = SyncWorker()
        self._worker.status_changed.connect(self._on_status_changed)
        self._worker.light_updated.connect(self._on_light_updated)
        self._worker.position_updated.connect(self._map_panel.on_position_updated)
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
            "running":   "○",
            "connected": "●",
            "waiting":   "○",
            "stopped":   "■",
            "error":     "✕",
        }
        icon = icons.get(status, "●")
        labels = {
            "running":   "Running — waiting for game",
            "connected": "Game connected",
            "waiting":   "Game disconnected",
            "stopped":   "Stopped",
            "error":     "Error — check settings",
        }
        text = labels.get(status, status)
        self._status_label.setText(f"{icon} {text}")
        self._state.update(status=status)

        if status in ("stopped", "error"):
            self._on_worker_finished()

    def _on_light_updated(
        self, game_day: int, game_time: int, brightness: int, kelvin: int,
        tz_name: str, country_name: str,
    ) -> None:
        game_str = f"{game_time // 60:02d}:{game_time % 60:02d}"
        self._status_label.setText(f"● Game connected   Day: {game_day}  Game: {game_str}")
        self._values_label.setText(
            f"Brightness: {brightness}/255   Color temp: {kelvin} K"
        )
        if tz_name:
            self._tz_label.setText(f"Timezone: {tz_name}")
        else:
            self._tz_label.setText("Timezone: unknown")
        self._country_label.setText(f"Country: {country_name or '—'}")

        self._state.update(
            status="connected",
            game_day=game_day,
            game_time=game_time,
            brightness=brightness,
            kelvin=kelvin,
            tz_name=tz_name or None,
            country=country_name or None,
        )

        # Forward to map panel
        self._map_panel.on_light_updated(game_day, game_time, brightness, kelvin, tz_name, country_name)

    def _on_worker_finished(self) -> None:
        self._start_btn.setEnabled(True)
        self._stop_btn.setEnabled(False)
        self._tray.set_running(False)
        self._values_label.setText("Brightness: --   Color temp: --")
        self._tz_label.setText("Timezone: --")
        self._country_label.setText("Country: --")
        self._state.update(status="stopped")

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

    def _on_theme_changed(self, name: str) -> None:
        theme.apply(name)
        cfg = config.load()
        cfg["theme"] = name
        config.save(cfg)

    def _copy_logs(self) -> None:
        QApplication.clipboard().setText(self._log_view.toPlainText())

    def _open_settings(self) -> None:
        dlg = SettingsDialog(self)
        if dlg.exec() and self._worker and self._worker.isRunning():
            # Restart worker with new config
            self._worker.stop()
            self._worker.wait()
            self.start_sync()

    # ── Web dashboard ─────────────────────────────────────────────────────────

    def _show_web_dialog(self) -> None:
        _WebDialog(self._web.url, self).exec()

    # ── Action drain (web → GUI thread) ──────────────────────────────────────

    def _drain_pending_actions(self) -> None:
        while True:
            action = self._state.pop_pending()
            if action is None:
                break
            if action == "start":
                self.start_sync()
            elif action == "stop":
                self.stop_sync()

    # ── Close → hide to tray ─────────────────────────────────────────────────

    def closeEvent(self, event: QCloseEvent) -> None:
        event.ignore()
        self.hide()
        self._tray.showMessage(
            "ETS2 Light Sync",
            "Still running in the system tray.",
            make_icon(),
            2000,
        )


# ── QR Code dialog ────────────────────────────────────────────────────────────

class _WebDialog(QDialog):
    """Small dialog that shows the web dashboard URL + QR code."""

    def __init__(self, url: str, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Dashboard no Celular")
        self.setFixedSize(300, 380)

        layout = QVBoxLayout(self)
        layout.setSpacing(12)
        layout.setContentsMargins(20, 20, 20, 20)

        title = QLabel("Escaneie com a câmera do celular")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title.setStyleSheet("font-size: 13px; font-weight: bold;")
        layout.addWidget(title)

        # QR code image
        qr_label = QLabel()
        qr_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        pixmap = _make_qr_pixmap(url, size=220)
        if pixmap:
            qr_label.setPixmap(pixmap)
        else:
            qr_label.setText("(instale qrcode[pil] para ver o QR)")
        layout.addWidget(qr_label)

        # URL as clickable text
        url_label = QLabel(f'<a href="{url}">{url}</a>')
        url_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        url_label.setOpenExternalLinks(True)
        url_label.setTextFormat(Qt.TextFormat.RichText)
        url_label.setStyleSheet("font-size: 11px;")
        url_label.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextBrowserInteraction
        )
        layout.addWidget(url_label)

        hint = QLabel("Ambos na mesma rede Wi-Fi")
        hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
        hint.setStyleSheet("font-size: 10px; color: grey;")
        layout.addWidget(hint)

        close_btn = QPushButton("Fechar")
        close_btn.clicked.connect(self.accept)
        layout.addWidget(close_btn)


def _make_qr_pixmap(url: str, size: int = 220) -> QPixmap | None:
    """Generate a QR code image and return it as a QPixmap, or None on error."""
    try:
        import qrcode  # type: ignore[import]
        qr = qrcode.QRCode(version=1, box_size=7, border=3)
        qr.add_data(url)
        qr.make(fit=True)
        img = qr.make_image(fill_color="black", back_color="white")

        buf = io.BytesIO()
        img.save(buf, format="PNG")
        pixmap = QPixmap()
        pixmap.loadFromData(buf.getvalue())
        return pixmap.scaled(
            size, size,
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
    except Exception as exc:
        log.debug("QR code generation failed: %s", exc)
        return None


# ── Logging handler that mirrors to AppState ──────────────────────────────────

class _StateLogHandler(logging.Handler):
    """Forwards log records to AppState.add_log() for the web dashboard."""

    def __init__(self, state: AppState) -> None:
        super().__init__()
        self._state = state

    def emit(self, record: logging.LogRecord) -> None:
        try:
            self._state.add_log(self.format(record))
        except Exception:
            self.handleError(record)
