"""
app/sync_worker.py – QThread that runs the ETS2 → HA sync loop.

Mirrors main.py logic but runs in a background thread so the UI stays
responsive.  Configuration is read from config/settings.json instead of .env.
"""

import logging
import os
import time
from typing import Optional

from PyQt6.QtCore import QThread, pyqtSignal

from app.config import load as load_config
from ha_client import HomeAssistantClient
from light_curve import calculate_light
from telemetry import get_game_time

log = logging.getLogger(__name__)


class SyncWorker(QThread):
    """Background thread that polls ETS2 telemetry and drives HA lights."""

    status_changed = pyqtSignal(str)           # "running" | "connected" | "waiting" | "stopped" | "error"
    light_updated = pyqtSignal(int, int, int)  # game_time_min, brightness, kelvin

    def __init__(self) -> None:
        super().__init__()
        self._running = False

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

        # Populate env vars so HomeAssistantClient.__init__ can read them.
        os.environ["HA_URL"] = str(cfg["ha_url"])
        os.environ["HA_TOKEN"] = str(cfg["ha_token"])
        os.environ["ENTITY_ID"] = str(cfg["entity_id"])
        os.environ["TRANSITION_TIME"] = str(cfg["transition_time"])
        os.environ["DEFAULT_BRIGHTNESS"] = str(cfg["default_brightness"])
        os.environ["DEFAULT_COLOR_TEMP_K"] = str(cfg["default_color_temp_k"])

        try:
            client = HomeAssistantClient()
        except ValueError as exc:
            log.error("Configuration error: %s", exc)
            self.status_changed.emit("error")
            return

        poll_interval = float(cfg.get("poll_interval", 15))
        self._running = True
        game_was_running = False

        log.info("ETS2 Light Sync starting  [poll=%.1fs]", poll_interval)
        self.status_changed.emit("running")

        while self._running:
            game_time: Optional[int] = get_game_time()

            if game_time is None:
                if game_was_running:
                    log.info("Game disconnected — resetting light")
                    client.reset_to_default()
                    game_was_running = False
                    self.status_changed.emit("waiting")
            else:
                if not game_was_running:
                    log.info("Game connected")
                    game_was_running = True
                    self.status_changed.emit("connected")

                brightness, color_temp = calculate_light(game_time)
                log.info(
                    "Game %02d:%02d  →  brightness=%3d/255  color_temp=%dK",
                    game_time // 60, game_time % 60, brightness, color_temp,
                )
                client.set_light(brightness, color_temp)
                self.light_updated.emit(game_time, brightness, color_temp)

            # Sleep in 0.5 s increments so stop() is responsive.
            elapsed = 0.0
            while self._running and elapsed < poll_interval:
                time.sleep(0.5)
                elapsed += 0.5

        # ── Cleanup (FR04) ────────────────────────────────────────────────────
        log.info("Shutting down — resetting light to default")
        client.reset_to_default()
        log.info("Goodbye.")
        self.status_changed.emit("stopped")
