"""
app/state.py – Estado compartilhado thread-safe.

Uma instância de AppState é mantida pela camada GUI e compartilhada com:
  - Sinais do SyncWorker (atualizam valores a cada ciclo de poll)
  - WebServer            (lê snapshot para a REST API)

Requisições de ação cross-thread (start/stop do browser) usam uma deque
que a thread GUI drena via QTimer.
"""

import math
import threading
from collections import deque
from typing import Optional


class AppState:
    """Container thread-safe com valores atuais e ações pendentes."""

    def __init__(self) -> None:
        self._lock = threading.Lock()

        # ── Valores de telemetria / sync ──────────────────────────────────────
        self.status: str = "stopped"
        self.game_time: int = 0       # minutos desde meia-noite, 0-1439
        self.game_day: int = 0
        self.brightness: int = 0      # 0-255
        self.kelvin: int = 6500
        self.tz_name: Optional[str] = None    # ex: "Europe/Copenhagen"
        self.country: Optional[str] = None    # ex: "Denmark"
        self.truck_x: float = float("nan")    # coordenada X do jogo (Leste)
        self.truck_z: float = float("nan")    # coordenada Z do jogo

        # ── Buffer de logs ────────────────────────────────────────────────────
        self._logs: list[str] = []
        self._max_logs: int = 200

        # ── Fila de ações cross-thread (web → GUI) ────────────────────────────
        self._pending: deque[str] = deque()

    # ── Escrita (qualquer thread) ─────────────────────────────────────────────

    def update(self, **kwargs) -> None:
        with self._lock:
            for k, v in kwargs.items():
                setattr(self, k, v)

    def add_log(self, line: str) -> None:
        with self._lock:
            self._logs.append(line)
            if len(self._logs) > self._max_logs:
                self._logs = self._logs[-self._max_logs:]

    def request_start(self) -> None:
        self._pending.append("start")

    def request_stop(self) -> None:
        self._pending.append("stop")

    # ── Leitura (qualquer thread) ─────────────────────────────────────────────

    def snapshot(self) -> dict:
        with self._lock:
            h, m = divmod(self.game_time, 60)
            tx = None if math.isnan(self.truck_x) else round(self.truck_x)
            tz = None if math.isnan(self.truck_z) else round(self.truck_z)
            return {
                "status":     self.status,
                "game_time":  f"{h:02d}:{m:02d}",
                "game_day":   self.game_day,
                "brightness": self.brightness,
                "kelvin":     self.kelvin,
                "tz_name":    self.tz_name,
                "country":    self.country,
                "truck_x":    tx,
                "truck_z":    tz,
            }

    def get_logs(self, last_n: int = 100) -> list[str]:
        with self._lock:
            return list(self._logs[-last_n:])

    # ── Drain de ações (thread GUI) ───────────────────────────────────────────

    def pop_pending(self) -> Optional[str]:
        try:
            return self._pending.popleft()
        except IndexError:
            return None
