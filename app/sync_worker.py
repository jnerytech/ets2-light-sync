"""
app/sync_worker.py – QThread that runs the ETS2 → HA sync loop.

Mirrors main.py logic but runs in a background thread so the UI stays
responsive.  Configuration is read from config/settings.json instead of .env.
"""

import logging
import time
from typing import Optional

from PyQt6.QtCore import QThread, pyqtSignal

from app.config import load as load_config
from ha_client import HomeAssistantClient
from light_curve import calculate_light
from location import get_location, reset_cache
from sun_times import get_sun_curve, reset_cache as reset_sun_cache
from telemetry import get_telemetry


log = logging.getLogger(__name__)


class SyncWorker(QThread):
    """Background thread that polls ETS2 telemetry and drives HA lights."""

    status_changed  = pyqtSignal(str)                       # "running"|"connected"|"waiting"|"stopped"|"error"
    light_updated   = pyqtSignal(int, int, int, int, str, str)  # game_day, game_time, brightness, kelvin, tz_name, country_name
    position_updated = pyqtSignal(float, float)             # truck_x, truck_z (for map widget)

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
            log.error("HA token is not set — open Settings and enter your token.")
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
            log.error("Configuration error: %s", exc)
            self.status_changed.emit("error")
            return

        # Load custom light curve (list-of-lists from JSON → list-of-tuples)
        raw_curve = cfg.get("light_curve")
        base_curve = [tuple(wp) for wp in raw_curve] if raw_curve else None

        astronomical_lighting = bool(cfg.get("astronomical_lighting", True))
        poll_interval = float(cfg.get("poll_interval", 5))

        if not self._running:  # stop() was called before run() had a chance to start
            self.status_changed.emit("stopped")
            return

        game_was_running = False

        log.info("ETS2 Light Sync starting  [poll=%.1fs]", poll_interval)
        self.status_changed.emit("running")

        while self._running:
            telemetry = get_telemetry()
            if telemetry is None:
                game_time: Optional[int] = None
                game_day = 0
                truck_x = truck_z = float("nan")
            else:
                game_time = telemetry.game_time
                game_day  = telemetry.game_day
                truck_x   = telemetry.truck_x
                truck_z   = telemetry.truck_z

            if game_time is None:
                if game_was_running:
                    log.info("Game disconnected — resetting light")
                    client.reset_to_default()
                    reset_cache()
                    reset_sun_cache()
                    game_was_running = False
                    self.status_changed.emit("waiting")
            else:
                if not game_was_running:
                    log.info("Game connected")
                    game_was_running = True
                    self.status_changed.emit("connected")

                # Resolve location and astronomical curve
                loc = get_location(truck_x, truck_z) if astronomical_lighting else None

                if loc and loc.tz_name:
                    dynamic_curve = get_sun_curve(loc.lat, loc.lon, loc.tz_name)
                else:
                    dynamic_curve = None

                active_curve = dynamic_curve or base_curve
                brightness, color_temp = calculate_light(game_time, active_curve)

                tz_name      = loc.tz_name      if loc else ""
                country_name = loc.country_name  if loc else ""

                if brightness == 0:
                    log.info(
                        "Game day %d  %02d:%02d  →  off  [%s]",
                        game_day, game_time // 60, game_time % 60,
                        tz_name or "UTC",
                    )
                else:
                    log.info(
                        "Game day %d  %02d:%02d  →  brightness=%3d/255  color_temp=%dK  [%s]",
                        game_day, game_time // 60, game_time % 60,
                        brightness, color_temp,
                        tz_name or "UTC",
                    )
                client.set_light(brightness, color_temp)
                self.light_updated.emit(
                    game_day, game_time, brightness, color_temp,
                    tz_name or "", country_name or "",
                )
                self.position_updated.emit(truck_x, truck_z)

            # Sleep in 0.5 s increments so stop() is responsive.
            elapsed = 0.0
            while self._running and elapsed < poll_interval:
                time.sleep(0.5)
                elapsed += 0.5

        # ── Cleanup ───────────────────────────────────────────────────────────
        log.info("Shutting down — resetting light to default")
        client.reset_to_default()
        log.info("Goodbye.")
        self.status_changed.emit("stopped")
