"""
ha_client.py – Home Assistant REST API client.

Sends light commands to a Home Assistant instance on the local network via
its REST API.  Network errors are logged as warnings and silently ignored so
the main sync loop keeps running (NFR03).
"""

import logging
import os
from typing import Any

import requests
from dotenv import load_dotenv

load_dotenv()

log = logging.getLogger(__name__)


class HomeAssistantClient:
    """Thin wrapper around the HA light services REST API."""

    def __init__(self) -> None:
        self.url = os.getenv("HA_URL", "http://192.168.3.155:8123").rstrip("/")
        self.token = os.getenv("HA_TOKEN")
        self.entity_id = os.getenv("ENTITY_ID", "light.luz")
        self.transition = float(os.getenv("TRANSITION_TIME", "1"))
        self.default_brightness = int(os.getenv("DEFAULT_BRIGHTNESS", "255"))
        self.default_color_temp_k = int(os.getenv("DEFAULT_COLOR_TEMP_K", "4000"))

        if not self.token:
            raise ValueError("HA_TOKEN is not set. Add it to your .env file.")

        self._headers = {
            "Authorization": f"Bearer {self.token}",
            "Content-Type": "application/json",
        }

    # ── Public API ───────────────────────────────────────────────────────────

    def set_light(self, brightness: int, color_temp_kelvin: int) -> None:
        """Set brightness and colour temperature.  brightness=0 turns the light off."""
        if brightness == 0:
            self._call("turn_off", {
                "entity_id": self.entity_id,
                "transition": self.transition,
            })
        else:
            mireds = _kelvin_to_mireds(color_temp_kelvin)
            self._call("turn_on", {
                "entity_id": self.entity_id,
                "brightness": brightness,
                "color_temp": mireds,
                "transition": self.transition,
            })

    def reset_to_default(self) -> None:
        """Restore the bulb to its default white/100% state (FR04)."""
        mireds = _kelvin_to_mireds(self.default_color_temp_k)
        self._call("turn_on", {
            "entity_id": self.entity_id,
            "brightness": self.default_brightness,
            "color_temp": mireds,
            "transition": 2,
        })
        log.info(
            "Light reset → brightness=%d, %dK (%d mireds)",
            self.default_brightness,
            self.default_color_temp_k,
            mireds,
        )

    # ── Internal helpers ─────────────────────────────────────────────────────

    def _call(self, service: str, payload: dict[str, Any]) -> None:
        endpoint = f"{self.url}/api/services/light/{service}"
        try:
            r = requests.post(endpoint, headers=self._headers, json=payload, timeout=5)
            r.raise_for_status()
            log.debug("HA %s → %d", service, r.status_code)
        except requests.RequestException as exc:
            log.warning("HA request failed (will retry next cycle): %s", exc)


def _kelvin_to_mireds(kelvin: int) -> int:
    """Convert colour temperature from Kelvin to mireds (µrc)."""
    return round(1_000_000 / kelvin)
