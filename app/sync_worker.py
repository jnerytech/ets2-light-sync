"""
app/sync_worker.py – QThread that runs the ETS2 → HA sync loop.

Mirrors main.py logic but runs in a background thread so the UI stays
responsive.  Configuration is read from config/settings.json instead of .env.

Lighting is driven exclusively by game time (minutes since midnight) using
the static waypoint curve or a custom curve from settings.  Real-world
coordinate/timezone conversion is NOT used — game time alone determines
brightness and colour temperature.
"""

import logging
import math
import time
from typing import Optional

from PyQt6.QtCore import QThread, pyqtSignal

from app.config import load as load_config
from ha_client import HomeAssistantClient
from light_curve import calculate_light, DEFAULT_WAYPOINTS
from telemetry import get_telemetry


log = logging.getLogger(__name__)


class SyncWorker(QThread):
    """Background thread that polls ETS2 telemetry and drives HA lights."""

    status_changed = pyqtSignal(str)  # "running"|"connected"|"waiting"|"stopped"|"error"
    light_updated  = pyqtSignal(int, int, int, int, float, float)
    # args: game_day, game_time_minutes, brightness, kelvin, truck_x, truck_z

    def __init__(self) -> None:
        super().__init__()
        self._running = True  # Set False by stop(); True by default so stop() before run() works

    # ── Public API ────────────────────────────────────────────────────────────

    def stop(self) -> None:
        """Signal the worker to stop after the current sleep."""
        self._running = False

    # ── QThread entry point ───────────────────────────────────────────────────

    def run(self) -> None:
        cfg = load_config()

        if not cfg.get("ha_token"):
            log.error("Token HA não configurado — abra as Configurações e insira seu token.")
            self.status_changed.emit("error")
            return

        try:
            client = HomeAssistantClient(
                url=str(cfg["ha_url"]),
                token=str(cfg["ha_token"]),
                entity_id=str(cfg["entity_id"]),
                transition=float(cfg["transition_time"]),
                default_brightness=int(cfg["default_brightness"]),
                default_color_temp_k=int(cfg["default_color_temp_k"]),
            )
        except ValueError as exc:
            log.error("Erro de configuração: %s", exc)
            self.status_changed.emit("error")
            return

        # Load custom light curve (list-of-lists from JSON → list-of-tuples)
        raw_curve = cfg.get("light_curve")
        base_curve = [tuple(wp) for wp in raw_curve] if raw_curve else None

        poll_interval = float(cfg.get("poll_interval", 5))
        curve_label = "curva personalizada" if base_curve else "curva padrão"

        if not self._running:  # stop() was called before run() had a chance to start
            self.status_changed.emit("stopped")
            return

        game_was_running = False

        log.info(
            "ETS2 Light Sync iniciando  [poll=%.1fs  %s]",
            poll_interval, curve_label,
        )
        _log_curve_summary(base_curve or list(DEFAULT_WAYPOINTS))
        self.status_changed.emit("running")

        while self._running:
            telemetry = get_telemetry()

            if telemetry is None:
                game_time: Optional[int] = None
                game_day = 0
                paused = False
                truck_x = truck_z = float("nan")
            else:
                game_time = telemetry.game_time
                game_day  = telemetry.game_day
                paused    = telemetry.paused
                truck_x   = telemetry.truck_x
                truck_z   = telemetry.truck_z

            if game_time is None:
                if game_was_running:
                    log.info("Jogo desconectado — resetando luz para o padrão")
                    client.reset_to_default()
                    game_was_running = False
                    self.status_changed.emit("waiting")
                else:
                    log.debug("Aguardando conexão com o jogo...")
            else:
                if not game_was_running:
                    log.info(
                        "Jogo conectado  [Dia %d  %s%s]",
                        game_day,
                        _fmt(game_time),
                        "  (pausado)" if paused else "",
                    )
                    game_was_running = True
                    self.status_changed.emit("connected")

                # Lighting driven purely by game time — no real-world coordinates
                brightness, color_temp = calculate_light(game_time, base_curve)

                coords_str = (
                    f"X={truck_x:.0f} Z={truck_z:.0f}"
                    if not (math.isnan(truck_x) or math.isnan(truck_z))
                    else "coords=N/A"
                )

                if brightness == 0:
                    log.info(
                        "Dia %d  %s%s  →  LUZ APAGADA  [%s]",
                        game_day, _fmt(game_time),
                        "  (pausado)" if paused else "",
                        coords_str,
                    )
                else:
                    log.info(
                        "Dia %d  %s%s  →  brilho=%3d/255  temp=%dK  [%s]",
                        game_day, _fmt(game_time),
                        "  (pausado)" if paused else "",
                        brightness, color_temp,
                        coords_str,
                    )

                client.set_light(brightness, color_temp)
                self.light_updated.emit(
                    game_day, game_time, brightness, color_temp,
                    truck_x, truck_z,
                )

            # Sleep in 0.5 s increments so stop() is responsive.
            elapsed = 0.0
            while self._running and elapsed < poll_interval:
                time.sleep(0.5)
                elapsed += 0.5

        # ── Cleanup ───────────────────────────────────────────────────────────
        log.info("Encerrando — resetando luz para o padrão")
        client.reset_to_default()
        log.info("Até logo.")
        self.status_changed.emit("stopped")


# ── Helpers ───────────────────────────────────────────────────────────────────

def _fmt(minutes: int) -> str:
    return f"{minutes // 60:02d}:{minutes % 60:02d}"


def _log_curve_summary(curve: list) -> None:
    """Log a compact summary of active waypoints for debugging."""
    log.debug("Curva de luz ativa (%d pontos):", len(curve))
    for minutes, brightness, kelvin in curve:
        log.debug("  %s  →  brilho=%3d/255  %dK", _fmt(minutes), brightness, kelvin)
