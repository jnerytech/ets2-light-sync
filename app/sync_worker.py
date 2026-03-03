"""
app/sync_worker.py – QThread que executa o loop de sincronização ETS2 → HA.

Espelha a lógica do main.py mas em background thread para a UI não travar.
Configuração vem de config/settings.json em vez de .env.

Pipeline:
  coordenadas X/Z do jogo
    → location.py  → lat/lon real + timezone + país
    → sun_times.py → curva dinâmica com nascer/pôr do sol reais
    → light_curve.py → brilho + temperatura de cor
    → ha_client.py → Home Assistant
"""

import logging
import math
import time
from typing import Optional

from PyQt6.QtCore import QThread, pyqtSignal

from app.config import load as load_config
from ha_client import HomeAssistantClient
from light_curve import calculate_light, DEFAULT_WAYPOINTS
from location import get_location, reset_cache as reset_loc_cache
from sun_times import get_sun_curve, reset_cache as reset_sun_cache
from telemetry import get_telemetry


log = logging.getLogger(__name__)


class SyncWorker(QThread):
    """Thread de fundo que lê telemetria ETS2 e controla luzes HA."""

    status_changed = pyqtSignal(str)
    # "running"|"connected"|"waiting"|"stopped"|"error"

    light_updated = pyqtSignal(int, int, int, int, str, str, float, float)
    # game_day, game_time_min, brightness, kelvin, tz_name, country, truck_x, truck_z

    def __init__(self) -> None:
        super().__init__()
        self._running = True

    # ── API pública ───────────────────────────────────────────────────────────

    def stop(self) -> None:
        self._running = False

    # ── Entrada do QThread ────────────────────────────────────────────────────

    def run(self) -> None:
        cfg = load_config()

        if not cfg.get("ha_token"):
            log.error("Token HA não configurado — abra as Configurações.")
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

        raw_curve = cfg.get("light_curve")
        base_curve = [tuple(wp) for wp in raw_curve] if raw_curve else None
        astronomical = cfg.get("astronomical_lighting", True)
        poll_interval = float(cfg.get("poll_interval", 5))

        curve_label = "personalizada" if base_curve else ("astronômica" if astronomical else "estática padrão")

        if not self._running:
            self.status_changed.emit("stopped")
            return

        log.info(
            "ETS2 Light Sync iniciando  [poll=%.1fs  curva=%s]",
            poll_interval, curve_label,
        )
        if not astronomical:
            _log_curve_summary(base_curve or list(DEFAULT_WAYPOINTS))

        self.status_changed.emit("running")

        game_was_running = False

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

            # ── Jogo desconectado ─────────────────────────────────────────────
            if game_time is None:
                if game_was_running:
                    log.info("Jogo desconectado — resetando luz para o padrão")
                    client.reset_to_default()
                    game_was_running = False
                    reset_loc_cache()
                    reset_sun_cache()
                    self.status_changed.emit("waiting")
                else:
                    log.debug("Aguardando conexão com o jogo...")

            # ── Jogo conectado ────────────────────────────────────────────────
            else:
                if not game_was_running:
                    log.info(
                        "Jogo conectado  [Dia %d  %s%s]",
                        game_day, _fmt(game_time),
                        "  (pausado)" if paused else "",
                    )
                    reset_loc_cache()
                    reset_sun_cache()
                    game_was_running = True
                    self.status_changed.emit("connected")

                # ── Resolução de localização ──────────────────────────────────
                tz_name = country = ""
                active_curve = base_curve

                if astronomical and not math.isnan(truck_x) and not math.isnan(truck_z):
                    loc = get_location(truck_x, truck_z)
                    if loc and loc.tz_name:
                        tz_name = loc.tz_name
                        country = loc.country_name or ""
                        sun_curve = get_sun_curve(loc.lat, loc.lon, loc.tz_name)
                        if sun_curve:
                            active_curve = sun_curve

                # ── Cálculo de brilho ─────────────────────────────────────────
                brightness, color_temp = calculate_light(game_time, active_curve)

                coords_str = (
                    f"X={truck_x:.0f} Z={truck_z:.0f}"
                    if not (math.isnan(truck_x) or math.isnan(truck_z))
                    else "coords=N/A"
                )

                if brightness == 0:
                    log.info(
                        "Dia %d  %s%s  →  LUZ APAGADA  [%s]%s",
                        game_day, _fmt(game_time),
                        "  (pausado)" if paused else "",
                        coords_str,
                        f"  tz={tz_name}" if tz_name else "",
                    )
                else:
                    log.info(
                        "Dia %d  %s%s  →  brilho=%3d/255  %dK  [%s]%s",
                        game_day, _fmt(game_time),
                        "  (pausado)" if paused else "",
                        brightness, color_temp,
                        coords_str,
                        f"  tz={tz_name}" if tz_name else "",
                    )

                client.set_light(brightness, color_temp)
                self.light_updated.emit(
                    game_day, game_time, brightness, color_temp,
                    tz_name, country,
                    truck_x, truck_z,
                )

            # ── Espera com interrupção rápida ─────────────────────────────────
            elapsed = 0.0
            while self._running and elapsed < poll_interval:
                time.sleep(0.5)
                elapsed += 0.5

        # ── Encerramento ──────────────────────────────────────────────────────
        log.info("Encerrando — resetando luz para o padrão")
        client.reset_to_default()
        log.info("Até logo.")
        self.status_changed.emit("stopped")


# ── Helpers ───────────────────────────────────────────────────────────────────

def _fmt(minutes: int) -> str:
    return f"{minutes // 60:02d}:{minutes % 60:02d}"


def _log_curve_summary(curve: list) -> None:
    log.debug("Curva de luz ativa (%d pontos):", len(curve))
    for minutes, brightness, kelvin in curve:
        log.debug("  %s  →  brilho=%3d/255  %dK", _fmt(minutes), brightness, kelvin)
