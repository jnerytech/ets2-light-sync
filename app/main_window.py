"""
app/main_window.py – Janela principal do ETS2 Light Sync.

Exibe logs em tempo real, status de sincronização, botões Start/Stop/Settings.
Minimiza para a bandeja do sistema ao fechar.
"""

import io
import logging
import math

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
    QVBoxLayout,
    QWidget,
)

from app import config, theme
from app.icon import make_icon
from app.log_handler import QtLogHandler
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
        self.setMinimumSize(640, 480)

        self._worker: SyncWorker | None = None
        self._state = AppState()
        self._web = WebServer(self._state)
        self._web.start()

        self._build_ui()
        self._setup_logging()
        self._tray = TrayIcon(self, self)
        self._tray.show()

        self._action_timer = QTimer(self)
        self._action_timer.timeout.connect(self._drain_pending_actions)
        self._action_timer.start(500)

        log.info("ETS2 Light Sync pronto — clique em Iniciar para começar.")

    # ── Construção da UI ──────────────────────────────────────────────────────

    def _build_ui(self) -> None:
        central = QWidget()
        self.setCentralWidget(central)
        root = QVBoxLayout(central)
        root.setSpacing(4)
        root.setContentsMargins(8, 8, 8, 8)

        # ── Botões ────────────────────────────────────────────────────────────
        btn_layout = QHBoxLayout()

        self._start_btn = QPushButton("▶  Iniciar")
        self._start_btn.clicked.connect(self.start_sync)

        self._stop_btn = QPushButton("■  Parar")
        self._stop_btn.clicked.connect(self.stop_sync)
        self._stop_btn.setEnabled(False)

        self._settings_btn = QPushButton("⚙  Configurações")
        self._settings_btn.clicked.connect(self._open_settings)

        copy_btn = QPushButton("⎘  Copiar Logs")
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

        # ── Painel de status ──────────────────────────────────────────────────
        self._status_label = QLabel("● Aguardando jogo   Hora: --:--")
        self._status_label.setStyleSheet("font-weight: bold;")

        self._values_label = QLabel("Brilho: --   Temperatura: --")
        self._tz_label     = QLabel("Timezone: --   País: --")
        self._coords_label = QLabel("Coordenadas: --")

        root.addWidget(self._status_label)
        root.addWidget(self._values_label)
        root.addWidget(self._tz_label)
        root.addWidget(self._coords_label)

        # ── Log ───────────────────────────────────────────────────────────────
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
        self._log_handler.setLevel(logging.DEBUG)
        self._log_handler.log_emitted.connect(self._append_log)
        logging.getLogger().addHandler(self._log_handler)
        logging.getLogger().setLevel(logging.DEBUG)

        state_handler = _StateLogHandler(self._state)
        state_handler.setLevel(logging.DEBUG)
        logging.getLogger().addHandler(state_handler)

    # ── Controle de sync ──────────────────────────────────────────────────────

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
            self._stop_btn.setEnabled(False)

    # ── Handlers de sinal ─────────────────────────────────────────────────────

    def _on_status_changed(self, status: str) -> None:
        icons  = {"running": "○", "connected": "●", "waiting": "○",
                  "stopped": "■", "error": "✕"}
        labels = {"running":   "Executando — aguardando jogo",
                  "connected": "Jogo conectado",
                  "waiting":   "Jogo desconectado",
                  "stopped":   "Parado",
                  "error":     "Erro — verifique as configurações"}
        self._status_label.setText(f"{icons.get(status,'●')} {labels.get(status, status)}")
        self._state.update(status=status)
        if status in ("stopped", "error"):
            self._on_worker_finished()

    def _on_light_updated(
        self,
        game_day: int, game_time: int, brightness: int, kelvin: int,
        tz_name: str, country: str,
        truck_x: float, truck_z: float,
    ) -> None:
        game_str = f"{game_time // 60:02d}:{game_time % 60:02d}"
        self._status_label.setText(
            f"● Jogo conectado   Dia: {game_day}   Hora: {game_str}"
        )
        self._values_label.setText(
            f"Brilho: {brightness}/255   Temperatura: {kelvin} K"
        )
        self._tz_label.setText(
            f"Timezone: {tz_name or '—'}   País: {country or '—'}"
        )
        if not (math.isnan(truck_x) or math.isnan(truck_z)):
            self._coords_label.setText(
                f"Coordenadas ETS2: X={truck_x:.0f}   Z={truck_z:.0f}"
            )
        else:
            self._coords_label.setText("Coordenadas ETS2: N/A")

        self._state.update(
            status="connected",
            game_day=game_day,
            game_time=game_time,
            brightness=brightness,
            kelvin=kelvin,
            tz_name=tz_name or None,
            country=country or None,
            truck_x=truck_x,
            truck_z=truck_z,
        )

    def _on_worker_finished(self) -> None:
        self._start_btn.setEnabled(True)
        self._stop_btn.setEnabled(False)
        self._tray.set_running(False)
        self._values_label.setText("Brilho: --   Temperatura: --")
        self._tz_label.setText("Timezone: --   País: --")
        self._coords_label.setText("Coordenadas ETS2: --")
        self._state.update(status="stopped")

    def _append_log(self, msg: str) -> None:
        self._log_view.appendPlainText(msg)
        doc = self._log_view.document()
        while doc.blockCount() > _MAX_LOG_LINES:
            cursor = self._log_view.textCursor()
            cursor.movePosition(cursor.MoveOperation.Start)
            cursor.select(cursor.SelectionType.BlockUnderCursor)
            cursor.removeSelectedText()
            cursor.deleteChar()
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
            self._worker.stop()
            self._worker.wait()
            self.start_sync()

    def _show_web_dialog(self) -> None:
        _WebDialog(self._web.url, self).exec()

    def _drain_pending_actions(self) -> None:
        while True:
            action = self._state.pop_pending()
            if action is None:
                break
            if action == "start":
                self.start_sync()
            elif action == "stop":
                self.stop_sync()

    def closeEvent(self, event: QCloseEvent) -> None:
        event.ignore()
        self.hide()
        self._tray.showMessage(
            "ETS2 Light Sync",
            "Ainda executando na bandeja do sistema.",
            make_icon(),
            2000,
        )


# ── Diálogo de QR Code ────────────────────────────────────────────────────────

class _WebDialog(QDialog):
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

        qr_label = QLabel()
        qr_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        pixmap = _make_qr_pixmap(url, size=220)
        if pixmap:
            qr_label.setPixmap(pixmap)
        else:
            qr_label.setText("(instale qrcode[pil] para ver o QR)")
        layout.addWidget(qr_label)

        url_label = QLabel(f'<a href="{url}">{url}</a>')
        url_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        url_label.setOpenExternalLinks(True)
        url_label.setTextFormat(Qt.TextFormat.RichText)
        url_label.setStyleSheet("font-size: 11px;")
        url_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextBrowserInteraction)
        layout.addWidget(url_label)

        hint = QLabel("Ambos na mesma rede Wi-Fi")
        hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
        hint.setStyleSheet("font-size: 10px; color: grey;")
        layout.addWidget(hint)

        close_btn = QPushButton("Fechar")
        close_btn.clicked.connect(self.accept)
        layout.addWidget(close_btn)


def _make_qr_pixmap(url: str, size: int = 220) -> QPixmap | None:
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
        log.debug("Falha ao gerar QR code: %s", exc)
        return None


# ── Handler de log → AppState ─────────────────────────────────────────────────

class _StateLogHandler(logging.Handler):
    def __init__(self, state: AppState) -> None:
        super().__init__()
        self._state = state

    def emit(self, record: logging.LogRecord) -> None:
        try:
            self._state.add_log(self.format(record))
        except Exception:
            self.handleError(record)
