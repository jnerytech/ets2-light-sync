"""
main.py – ETS2 Light Sync orchestrator (headless mode).

Reads ETS2 telemetry, computes astronomical light settings from real
sunrise/sunset times for the truck's location, and sends them to
Home Assistant.  On exit it resets the bulb to its default state.

Simulation mode
───────────────
Set SIM_MODE=1 in .env (or environment) to run without ETS2.  The script
will simulate a full in-game day at SIM_TIME_SPEED game-minutes per second,
starting at SIM_TIME_START minutes since midnight.

Usage
─────
  python main.py              # normal mode
  SIM_MODE=1 python main.py   # simulation mode (Linux / PowerShell)
"""

import logging
import os
import signal
import time
from typing import Optional

from dotenv import load_dotenv

from ha_client import HomeAssistantClient
from light_curve import calculate_light
from location import get_location, reset_cache
from sun_times import get_sun_curve, reset_cache as reset_sun_cache
from telemetry import get_telemetry

load_dotenv()

# ── Configuration ────────────────────────────────────────────────────────────
POLL_INTERVAL         = float(os.getenv("POLL_INTERVAL", "15"))    # seconds
SIM_MODE              = os.getenv("SIM_MODE", "0") == "1"
SIM_TIME_START        = int(os.getenv("SIM_TIME_START", "360"))    # 06:00
SIM_TIME_SPEED        = float(os.getenv("SIM_TIME_SPEED", "60"))   # game-min/real-sec
ASTRONOMICAL_LIGHTING = os.getenv("ASTRONOMICAL_LIGHTING", "1") == "1"

# ── Logging ──────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger(__name__)

# ── State ────────────────────────────────────────────────────────────────────
_running = True
_sim_epoch: float = 0.0


def _shutdown(signum: int | None = None, frame: object | None = None) -> None:
    global _running
    _running = False


signal.signal(signal.SIGINT, _shutdown)
signal.signal(signal.SIGTERM, _shutdown)


# ── Helpers ──────────────────────────────────────────────────────────────────

def _sim_time() -> int:
    """Return simulated game time (0–1439 minutes) based on wall clock."""
    elapsed = time.monotonic() - _sim_epoch
    return int(SIM_TIME_START + elapsed * SIM_TIME_SPEED) % 1440


def _fmt(minutes: int) -> str:
    return f"{minutes // 60:02d}:{minutes % 60:02d}"


# ── Main loop ────────────────────────────────────────────────────────────────

def main() -> None:
    global _sim_epoch

    log.info(
        "ETS2 Light Sync starting  [poll=%.1fs%s%s]",
        POLL_INTERVAL,
        ", SIM MODE" if SIM_MODE else "",
        ", astronomical lighting" if ASTRONOMICAL_LIGHTING else "",
    )

    client = HomeAssistantClient()
    _sim_epoch = time.monotonic()

    game_was_running = False

    while _running:
        # ── Get current game time and truck position ───────────────────────
        if SIM_MODE:
            game_time: Optional[int] = _sim_time()
            truck_x = truck_z = float("nan")
        else:
            telemetry = get_telemetry()
            if telemetry is None:
                game_time = None
                truck_x = truck_z = float("nan")
            else:
                game_time = telemetry.game_time
                truck_x   = telemetry.truck_x
                truck_z   = telemetry.truck_z

        # ── Handle game connect / disconnect ──────────────────────────────
        if game_time is None:
            if game_was_running:
                log.info("Game disconnected — resetting light")
                client.reset_to_default()
                reset_cache()
                reset_sun_cache()
                game_was_running = False
            time.sleep(POLL_INTERVAL)
            continue

        if not game_was_running:
            log.info("Game connected")
            game_was_running = True

        # ── Resolve location and astronomical curve ────────────────────────
        loc = get_location(truck_x, truck_z) if ASTRONOMICAL_LIGHTING else None

        dynamic_curve = None
        if loc and loc.tz_name:
            dynamic_curve = get_sun_curve(loc.lat, loc.lon, loc.tz_name)
            if loc.tz_name:
                log.debug("TZ: %s  country: %s", loc.tz_name, loc.country_name or "unknown")

        # ── Calculate and apply light settings ────────────────────────────
        assert isinstance(game_time, int)
        brightness, color_temp = calculate_light(game_time, dynamic_curve)

        log.info(
            "Game %s  →  brightness=%3d/255  color_temp=%dK  [%s]",
            _fmt(game_time), brightness, color_temp,
            loc.tz_name if loc and loc.tz_name else "UTC",
        )
        client.set_light(brightness, color_temp)

        time.sleep(POLL_INTERVAL)

    # ── Cleanup on exit ───────────────────────────────────────────────────
    log.info("Shutting down — resetting light to default")
    client.reset_to_default()
    log.info("Goodbye.")


if __name__ == "__main__":
    main()
