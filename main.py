"""
main.py – ETS2 Light Sync orchestrator.

Reads ETS2 game time (FR01), calculates the matching light settings (FR02),
and sends them to Home Assistant (FR03).  On exit it resets the bulb to its
default state (FR04).  Poll rate is configurable via .env (FR05).

Simulation mode
───────────────
Set SIM_MODE=1 in .env (or environment) to run without ETS2.  The script
will simulate a full in-game day at SIM_TIME_SPEED game-minutes per second,
starting at SIM_TIME_START minutes since midnight.  Useful for tuning the
light curve without launching the game.

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
from telemetry import get_game_time

load_dotenv()

# ── Configuration ────────────────────────────────────────────────────────────
POLL_INTERVAL = float(os.getenv("POLL_INTERVAL", "1.0"))   # seconds (FR05)
SIM_MODE = os.getenv("SIM_MODE", "0") == "1"
SIM_TIME_START = int(os.getenv("SIM_TIME_START", "360"))   # 06:00
SIM_TIME_SPEED = float(os.getenv("SIM_TIME_SPEED", "60"))  # game-min per real-sec

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

    log.info("ETS2 Light Sync starting  [poll=%.1fs%s]",
             POLL_INTERVAL, ", SIM MODE" if SIM_MODE else "")

    client = HomeAssistantClient()
    _sim_epoch = time.monotonic()

    last_brightness: Optional[int] = None
    last_color_temp: Optional[int] = None
    game_was_running = False

    while _running:
        # ── Get current game time ──────────────────────────────────────────
        if SIM_MODE:
            game_time: Optional[int] = _sim_time()
        else:
            game_time = get_game_time()

        # ── Handle game connect / disconnect ──────────────────────────────
        if game_time is None:
            if game_was_running:
                log.info("Game disconnected — resetting light")
                client.reset_to_default()
                last_brightness = None
                last_color_temp = None
                game_was_running = False
            time.sleep(POLL_INTERVAL)
            continue

        if not game_was_running:
            log.info("Game connected")
            game_was_running = True

        # ── Calculate and (if changed) apply light settings ───────────────
        brightness, color_temp = calculate_light(game_time)

        if brightness != last_brightness or color_temp != last_color_temp:
            log.info(
                "Game %s  →  brightness=%3d/255  color_temp=%dK",
                _fmt(game_time), brightness, color_temp,
            )
            client.set_light(brightness, color_temp)
            last_brightness = brightness
            last_color_temp = color_temp

        time.sleep(POLL_INTERVAL)

    # ── Cleanup on exit (FR04) ────────────────────────────────────────────
    log.info("Shutting down — resetting light to default")
    client.reset_to_default()
    log.info("Goodbye.")


if __name__ == "__main__":
    main()
