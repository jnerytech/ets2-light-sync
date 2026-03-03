"""
location.py – Coordenadas ETS2 → LocationInfo real.

Converte as coordenadas world-space do caminhão (X=Leste, Z=Norte, unidade ≈ 1 m
na escala 1:19 do mapa ETS2 Europa) para latitude/longitude real e determina:
  - Nome da timezone IANA (via timezonefinder offline)
  - Nome do país (via data/ets2_countries.json)
  - Offset UTC em minutos (via zoneinfo, incluindo DST)

Calibração linear com dois pontos de ancoragem (Paris e Berlim):
  Paris:  ETS2(X=-31600, Z=-62000) → real(48.8566°N, 2.3522°E)
  Berlim: ETS2(X= 17400, Z=-39200) → real(52.5200°N, 13.4050°E)

Cache: o lookup de timezone é ignorado quando o caminhão se moveu menos de
_CACHE_THRESHOLD_UNITS unidades desde a última consulta bem-sucedida.
"""

import datetime
import json
import logging
import math
from pathlib import Path
from typing import NamedTuple, Optional
from zoneinfo import ZoneInfo

log = logging.getLogger(__name__)

# ── Constantes de calibração ───────────────────────────────────────────────────
# Dois pontos de referência: Paris e Berlim.
# Nota: no sistema ETS2, Z menos negativo = mais ao norte.

_REF_X   = -31600.0   # Paris ETS2 X (Leste)
_REF_Z   = -62000.0   # Paris ETS2 Z
_REF_LAT =  48.8566   # Paris latitude real
_REF_LON =   2.3522   # Paris longitude real

_SCALE_LON = (13.4050 - 2.3522) / (17400.0 - (-31600.0))   # ≈ 0.00022548 grau/unidade
_SCALE_LAT = (52.5200 - 48.8566) / (-39200.0 - (-62000.0))  # ≈ 0.00016074 grau/unidade

_CACHE_THRESHOLD_UNITS = 5000.0  # Re-consulta só quando mover > ~5 km

# ── Singleton TimezoneFinder ───────────────────────────────────────────────────
try:
    from timezonefinder import TimezoneFinder as _TFClass
    _TF: Optional[_TFClass] = _TFClass()
except ImportError:
    _TF = None  # type: ignore[assignment]

# ── Dados estáticos de países ─────────────────────────────────────────────────

def _load_countries() -> dict:
    try:
        path = Path(__file__).parent / "data" / "ets2_countries.json"
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        return data.get("by_timezone", {})
    except Exception as exc:
        log.warning("Não foi possível carregar ets2_countries.json: %s", exc)
        return {}

_COUNTRIES: dict = _load_countries()


# ── Tipo de resultado ─────────────────────────────────────────────────────────

class LocationInfo(NamedTuple):
    lat: float
    lon: float
    tz_name: Optional[str]
    country_name: Optional[str]
    utc_offset_minutes: int


# ── Conversão pura de coordenadas ─────────────────────────────────────────────

def ets2_to_latlon(x: float, z: float) -> tuple[float, float]:
    """Converte coordenadas ETS2 world-space para (latitude, longitude) reais."""
    lat = _REF_LAT + (z - _REF_Z) * _SCALE_LAT
    lon = _REF_LON + (x - _REF_X) * _SCALE_LON
    return lat, lon


def get_country_name(tz_name: str) -> Optional[str]:
    entry = _COUNTRIES.get(tz_name)
    return entry["name"] if entry else None


# ── Cache de localização ──────────────────────────────────────────────────────

class _LocationCache:
    """Resolve coordenadas ETS2 para LocationInfo com cache por posição."""

    def __init__(self, threshold_units: float = _CACHE_THRESHOLD_UNITS) -> None:
        self._threshold = threshold_units
        self._cached_x: Optional[float] = None
        self._cached_z: Optional[float] = None
        self._cached_info: Optional[LocationInfo] = None

    def get(self, truck_x: float, truck_z: float) -> Optional[LocationInfo]:
        if math.isnan(truck_x) or math.isnan(truck_z):
            return None
        if self._is_cache_hit(truck_x, truck_z):
            log.debug(
                "Location cache hit  [X=%.0f Z=%.0f]  tz=%s",
                truck_x, truck_z,
                self._cached_info.tz_name if self._cached_info else "N/A",
            )
            return self._cached_info
        info = self._resolve(truck_x, truck_z)
        self._cached_x, self._cached_z, self._cached_info = truck_x, truck_z, info
        return info

    def reset(self) -> None:
        self._cached_x = None
        self._cached_z = None
        self._cached_info = None
        log.debug("Cache de localização invalidado")

    def _is_cache_hit(self, x: float, z: float) -> bool:
        if self._cached_x is None or self._cached_z is None:
            return False
        return math.hypot(x - self._cached_x, z - self._cached_z) < self._threshold

    def _resolve(self, truck_x: float, truck_z: float) -> Optional[LocationInfo]:
        try:
            lat, lon = ets2_to_latlon(truck_x, truck_z)
            lat = max(-90.0, min(90.0, lat))
            lon = max(-180.0, min(180.0, lon))

            # ── Log de diagnóstico: sempre visível para facilitar calibração ──
            log.info(
                "Posição do jogo → conversão: X=%.0f Z=%.0f  →  lat=%.4f° lon=%.4f°",
                truck_x, truck_z, lat, lon,
            )

            if _TF is None:
                log.warning("timezonefinder não instalado — localização desabilitada")
                return LocationInfo(lat=lat, lon=lon, tz_name=None,
                                    country_name=None, utc_offset_minutes=0)

            tz_name = _TF.timezone_at(lat=lat, lng=lon)

            if tz_name is None:
                log.warning(
                    "Nenhuma timezone encontrada para lat=%.4f lon=%.4f "
                    "(posição convertida pode estar fora do mapa real — "
                    "verifique a calibração de coordenadas)",
                    lat, lon,
                )
                return LocationInfo(lat=lat, lon=lon, tz_name=None,
                                    country_name=None, utc_offset_minutes=0)

            tz = ZoneInfo(tz_name)
            now_utc = datetime.datetime.now(datetime.timezone.utc)
            utc_offset = now_utc.astimezone(tz).utcoffset()
            assert utc_offset is not None
            offset_minutes = int(utc_offset.total_seconds() // 60)
            country_name = get_country_name(tz_name)

            log.info(
                "Localização detectada: %s  (%s)  UTC%+.1fh  "
                "[lat=%.4f° lon=%.4f°  coords ETS2: X=%.0f Z=%.0f]",
                tz_name,
                country_name or "país desconhecido",
                offset_minutes / 60,
                lat, lon,
                truck_x, truck_z,
            )

            return LocationInfo(
                lat=lat, lon=lon,
                tz_name=tz_name,
                country_name=country_name,
                utc_offset_minutes=offset_minutes,
            )

        except Exception as exc:
            log.warning(
                "Falha no lookup de localização [X=%.0f Z=%.0f]: %s — usando UTC+0",
                truck_x, truck_z, exc,
            )
            return LocationInfo(lat=float("nan"), lon=float("nan"), tz_name=None,
                                country_name=None, utc_offset_minutes=0)


# ── Singleton público ─────────────────────────────────────────────────────────

_cache = _LocationCache()


def get_location(truck_x: float, truck_z: float) -> Optional[LocationInfo]:
    """Retorna LocationInfo para a posição ETS2 informada (com cache)."""
    return _cache.get(truck_x, truck_z)


def reset_cache() -> None:
    """Invalida o cache de posição (chamar no início de cada sessão)."""
    _cache.reset()
