"""
main.py – ETS2 Light Sync (modo headless).

Pipeline:
  telemetry.py  → coordenadas X/Z + horário do jogo
  location.py   → lat/lon + timezone + país
  sun_times.py  → curva dinâmica com nascer/pôr do sol reais
  light_curve.py → brilho + temperatura de cor
  ha_client.py  → Home Assistant

Uso:
  python main.py
"""

import logging
import math
import os
import signal
import time

from dotenv import load_dotenv

from ha_client import HomeAssistantClient
from light_curve import calculate_light
from location import get_location, reset_cache as reset_loc_cache
from sun_times import get_sun_curve, reset_cache as reset_sun_cache
from telemetry import get_telemetry

load_dotenv()

POLL_INTERVAL      = float(os.getenv("POLL_INTERVAL", "15"))
ASTRONOMICAL       = os.getenv("ASTRONOMICAL_LIGHTING", "true").lower() != "false"

logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger(__name__)

_running = True


def _shutdown(signum=None, frame=None) -> None:
    global _running
    _running = False


signal.signal(signal.SIGINT,  _shutdown)
signal.signal(signal.SIGTERM, _shutdown)


def _fmt(minutes: int) -> str:
    return f"{minutes // 60:02d}:{minutes % 60:02d}"


def main() -> None:
    mode = "astronômica" if ASTRONOMICAL else "estática padrão"
    log.info("ETS2 Light Sync iniciando  [poll=%.1fs  curva=%s]", POLL_INTERVAL, mode)

    client = HomeAssistantClient.from_env()
    game_was_running = False

    while _running:
        telemetry = get_telemetry()

        if telemetry is None:
            game_time = None
            game_day  = 0
            paused    = False
            truck_x   = truck_z = float("nan")
        else:
            game_time = telemetry.game_time
            game_day  = telemetry.game_day
            paused    = telemetry.paused
            truck_x   = telemetry.truck_x
            truck_z   = telemetry.truck_z

        # ── Jogo desconectado ─────────────────────────────────────────────────
        if game_time is None:
            if game_was_running:
                log.info("Jogo desconectado — resetando luz para o padrão")
                client.reset_to_default()
                game_was_running = False
                reset_loc_cache()
                reset_sun_cache()
            else:
                log.debug("Aguardando conexão com o jogo...")
            time.sleep(POLL_INTERVAL)
            continue

        # ── Jogo conectado ────────────────────────────────────────────────────
        if not game_was_running:
            log.info(
                "Jogo conectado  [Dia %d  %s%s]",
                game_day, _fmt(game_time),
                "  (pausado)" if paused else "",
            )
            reset_loc_cache()
            reset_sun_cache()
            game_was_running = True

        # ── Localização + curva ───────────────────────────────────────────────
        active_curve = None

        if ASTRONOMICAL and not (math.isnan(truck_x) or math.isnan(truck_z)):
            loc = get_location(truck_x, truck_z)
            if loc and loc.tz_name:
                sun_curve = get_sun_curve(loc.lat, loc.lon, loc.tz_name)
                if sun_curve:
                    active_curve = sun_curve

        # ── Cálculo de brilho ─────────────────────────────────────────────────
        brightness, color_temp = calculate_light(game_time, active_curve)

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
                "Dia %d  %s%s  →  brilho=%3d/255  %dK  [%s]",
                game_day, _fmt(game_time),
                "  (pausado)" if paused else "",
                brightness, color_temp,
                coords_str,
            )

        client.set_light(brightness, color_temp)
        time.sleep(POLL_INTERVAL)

    # ── Encerramento ──────────────────────────────────────────────────────────
    log.info("Encerrando — resetando luz para o padrão")
    client.reset_to_default()
    log.info("Até logo.")


if __name__ == "__main__":
    main()
