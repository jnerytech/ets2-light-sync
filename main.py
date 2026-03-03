"""
main.py – ETS2 Light Sync orchestrator (headless mode).

Reads ETS2 telemetry and computes light settings from game time alone.
Sends brightness and colour temperature to Home Assistant.
On exit it resets the bulb to its default state.

Lighting is driven exclusively by in-game time (minutes since midnight)
using the static waypoint curve — real-world coordinate/timezone conversion
is NOT used, so the light follows the game's day/night cycle directly.

Usage
─────
  python main.py
"""

import logging
import math
import os
import signal
import time

from dotenv import load_dotenv

from ha_client import HomeAssistantClient
from light_curve import calculate_light, DEFAULT_WAYPOINTS
from telemetry import get_telemetry

load_dotenv()  # populate os.environ from .env before reading values below

# ── Configuration ────────────────────────────────────────────────────────────
POLL_INTERVAL = float(os.getenv("POLL_INTERVAL", "15"))

# ── Logging ──────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger(__name__)

# ── State ────────────────────────────────────────────────────────────────────
_running = True


def _shutdown(signum: int | None = None, frame: object | None = None) -> None:
    global _running
    _running = False


signal.signal(signal.SIGINT, _shutdown)
signal.signal(signal.SIGTERM, _shutdown)


# ── Helpers ──────────────────────────────────────────────────────────────────

def _fmt(minutes: int) -> str:
    return f"{minutes // 60:02d}:{minutes % 60:02d}"


def _log_curve_summary() -> None:
    log.debug("Curva de luz ativa (%d pontos):", len(DEFAULT_WAYPOINTS))
    for minutes, brightness, kelvin in DEFAULT_WAYPOINTS:
        log.debug("  %s  →  brilho=%3d/255  %dK", _fmt(minutes), brightness, kelvin)


# ── Main loop ────────────────────────────────────────────────────────────────

def main() -> None:
    log.info("ETS2 Light Sync iniciando  [poll=%.1fs  curva padrão de horário do jogo]", POLL_INTERVAL)
    _log_curve_summary()

    client = HomeAssistantClient.from_env()
    game_was_running = False

    while _running:
        # ── Get current game time and truck position ───────────────────────
        telemetry = get_telemetry()

        if telemetry is None:
            game_time = None
            game_day = 0
            paused = False
            truck_x = truck_z = float("nan")
        else:
            game_time = telemetry.game_time
            game_day  = telemetry.game_day
            paused    = telemetry.paused
            truck_x   = telemetry.truck_x
            truck_z   = telemetry.truck_z

        # ── Handle game connect / disconnect ──────────────────────────────
        if game_time is None:
            if game_was_running:
                log.info("Jogo desconectado — resetando luz para o padrão")
                client.reset_to_default()
                game_was_running = False
            else:
                log.debug("Aguardando conexão com o jogo...")
            time.sleep(POLL_INTERVAL)
            continue

        if not game_was_running:
            log.info(
                "Jogo conectado  [Dia %d  %s%s]",
                game_day, _fmt(game_time),
                "  (pausado)" if paused else "",
            )
            game_was_running = True

        # ── Calculate light from game time only ────────────────────────────
        brightness, color_temp = calculate_light(game_time)

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

        time.sleep(POLL_INTERVAL)

    # ── Cleanup on exit ───────────────────────────────────────────────────
    log.info("Encerrando — resetando luz para o padrão")
    client.reset_to_default()
    log.info("Até logo.")


if __name__ == "__main__":
    main()
