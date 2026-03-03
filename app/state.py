"""
app/state.py – Thread-safe shared application state.

A single AppState instance is owned by the GUI layer and shared with:
  - SyncWorker signals (update telemetry values on each poll cycle)
  - WebServer        (reads a snapshot for the REST API)

Cross-thread action requests (start/stop from the web browser) use a
deque-based queue that the GUI thread drains via a QTimer, avoiding any
direct Qt calls from non-GUI threads.
"""

import math
import threading
from collections import deque
from typing import Optional


class AppState:
    """Thread-safe container for current sync values and pending UI actions."""

    def __init__(self) -> None:
        self._lock = threading.Lock()

        # ── Telemetry / sync values ───────────────────────────────────────────
        self.status: str = "stopped"
        self.game_time: int = 0       # minutes since midnight, 0-1439
        self.game_day: int = 0
        self.brightness: int = 0      # 0-255
        self.kelvin: int = 6500
        self.truck_x: float = float("nan")   # ETS2 world X coordinate (East)
        self.truck_z: float = float("nan")   # ETS2 world Z coordinate (South)

        # ── Rolling log buffer ────────────────────────────────────────────────
        self._logs: list[str] = []
        self._max_logs: int = 200

        # ── Cross-thread action queue (web → GUI thread) ──────────────────────
        # deque.append / deque.popleft are thread-safe in CPython (GIL).
        self._pending: deque[str] = deque()

    # ── Writes (any thread) ───────────────────────────────────────────────────

    def update(self, **kwargs) -> None:
        """Atomically update one or more state fields."""
        with self._lock:
            for k, v in kwargs.items():
                setattr(self, k, v)

    def add_log(self, line: str) -> None:
        with self._lock:
            self._logs.append(line)
            if len(self._logs) > self._max_logs:
                self._logs = self._logs[-self._max_logs:]

    def request_start(self) -> None:
        """Queue a start request to be consumed by the GUI thread."""
        self._pending.append("start")

    def request_stop(self) -> None:
        """Queue a stop request to be consumed by the GUI thread."""
        self._pending.append("stop")

    # ── Reads (any thread) ────────────────────────────────────────────────────

    def snapshot(self) -> dict:
        """Return a JSON-serialisable dict of the current state."""
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
                "truck_x":    tx,
                "truck_z":    tz,
            }

    def get_logs(self, last_n: int = 100) -> list[str]:
        with self._lock:
            return list(self._logs[-last_n:])

    # ── GUI-thread action drain ────────────────────────────────────────────────

    def pop_pending(self) -> Optional[str]:
        """Consume one queued action, or return None.

        Must be called only from the GUI thread (via a QTimer).
        """
        try:
            return self._pending.popleft()
        except IndexError:
            return None
