"""
location.py – ETS2 world coordinates → real-world LocationInfo.

Converts truck world-space coordinates (X=East, Z=South, game unit ≈ 1 m at
1:19 map scale) into a real-world latitude/longitude, then determines:
  - IANA timezone name (via offline timezonefinder)
  - Country display name (via static data/ets2_countries.json)
  - UTC offset in minutes (via zoneinfo, including DST)

A single TimezoneFinder instance is created once at import time (loading its
data file is expensive) and reused for every lookup.

Caching: timezone lookup is skipped when the truck has moved less than
_CACHE_THRESHOLD_UNITS game units from the last successful lookup position.
"""

import datetime
import json
import logging
import math
from pathlib import Path
from typing import NamedTuple, Optional
from zoneinfo import ZoneInfo

log = logging.getLogger(__name__)

# ── Calibration constants ──────────────────────────────────────────────────────
# Derived from two known city positions in ETS2 world-space vs real geography.
#   Paris:  ETS2 (X=-31600, Z=-62000) → real (lat=48.8566, lon=2.3522)
#   Berlin: ETS2 (X= 17400, Z=-39200) → real (lat=52.5200, lon=13.4050)

_REF_X   = -31600.0   # Paris ETS2 X (East)
_REF_Z   = -62000.0   # Paris ETS2 Z (South)
_REF_LAT =  48.8566   # Paris real latitude
_REF_LON =   2.3522   # Paris real longitude

_SCALE_LON = (13.4050 - 2.3522) / (17400.0 - (-31600.0))   # ≈ 0.00022548 deg/unit
_SCALE_LAT = (52.5200 - 48.8566) / (-39200.0 - (-62000.0))  # ≈ 0.00016074 deg/unit

_CACHE_THRESHOLD_UNITS = 5000.0  # Re-query only when truck moves > ~5 km

# ── TimezoneFinder singleton ───────────────────────────────────────────────────
# Constructed once — loading the data file is slow (~0.5 s).
try:
    from timezonefinder import TimezoneFinder as _TFClass
    _TF: Optional[_TFClass] = _TFClass()
except ImportError:
    _TF = None  # type: ignore[assignment]

# ── Static country data ────────────────────────────────────────────────────────

def _load_countries() -> dict:
    try:
        path = Path(__file__).parent / "data" / "ets2_countries.json"
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        return data.get("by_timezone", {})
    except Exception as exc:
        log.warning("Could not load ets2_countries.json: %s", exc)
        return {}

_COUNTRIES: dict = _load_countries()


# ── LocationInfo result type ───────────────────────────────────────────────────

class LocationInfo(NamedTuple):
    lat: float
    lon: float
    tz_name: Optional[str]        # IANA timezone name, e.g. "Europe/Berlin"
    country_name: Optional[str]   # Display name, e.g. "Germany"
    utc_offset_minutes: int       # UTC offset including DST, e.g. +120 for CEST


# ── Pure coordinate conversion ────────────────────────────────────────────────

def ets2_to_latlon(x: float, z: float) -> tuple[float, float]:
    """Convert ETS2 world coordinates to real-world (latitude, longitude)."""
    lat = _REF_LAT + (z - _REF_Z) * _SCALE_LAT
    lon = _REF_LON + (x - _REF_X) * _SCALE_LON
    return lat, lon


def get_country_name(tz_name: str) -> Optional[str]:
    """Return country display name for a given IANA timezone name, or None."""
    entry = _COUNTRIES.get(tz_name)
    return entry["name"] if entry else None


# ── Location cache ─────────────────────────────────────────────────────────────

class _LocationCache:
    """Resolves ETS2 truck coordinates to LocationInfo, with position-based caching."""

    def __init__(self, threshold_units: float = _CACHE_THRESHOLD_UNITS) -> None:
        self._threshold = threshold_units
        self._cached_x: Optional[float] = None
        self._cached_z: Optional[float] = None
        self._cached_info: Optional[LocationInfo] = None

    def get(self, truck_x: float, truck_z: float) -> Optional[LocationInfo]:
        """Return LocationInfo for the given ETS2 position, using cache when available."""
        if math.isnan(truck_x) or math.isnan(truck_z):
            return None
        if self._is_cache_hit(truck_x, truck_z):
            return self._cached_info
        info = self._resolve(truck_x, truck_z)
        self._cached_x, self._cached_z, self._cached_info = truck_x, truck_z, info
        return info

    def reset(self) -> None:
        """Invalidate the cache (call at game session start)."""
        self._cached_x = None
        self._cached_z = None
        self._cached_info = None

    def _is_cache_hit(self, x: float, z: float) -> bool:
        if self._cached_x is None or self._cached_z is None:
            return False
        return math.hypot(x - self._cached_x, z - self._cached_z) < self._threshold

    def _resolve(self, truck_x: float, truck_z: float) -> Optional[LocationInfo]:
        try:
            lat, lon = ets2_to_latlon(truck_x, truck_z)
            lat = max(-90.0, min(90.0, lat))
            lon = max(-180.0, min(180.0, lon))

            if _TF is None:
                log.warning("timezonefinder not available — location lookup disabled")
                return LocationInfo(lat=lat, lon=lon, tz_name=None,
                                    country_name=None, utc_offset_minutes=0)

            tz_name = _TF.timezone_at(lat=lat, lng=lon)
            if tz_name is None:
                log.debug("No timezone at lat=%.4f lon=%.4f — using UTC+0", lat, lon)
                return LocationInfo(lat=lat, lon=lon, tz_name=None,
                                    country_name=None, utc_offset_minutes=0)

            tz = ZoneInfo(tz_name)
            now_utc = datetime.datetime.now(datetime.timezone.utc)
            utc_offset = now_utc.astimezone(tz).utcoffset()
            assert utc_offset is not None
            offset_minutes = int(utc_offset.total_seconds() // 60)
            country_name = get_country_name(tz_name)

            log.debug(
                "Location: %s  UTC%+.1f  country=%s  (lat=%.4f lon=%.4f)",
                tz_name, offset_minutes / 60, country_name or "unknown", lat, lon,
            )
            return LocationInfo(lat=lat, lon=lon, tz_name=tz_name,
                                country_name=country_name,
                                utc_offset_minutes=offset_minutes)

        except Exception as exc:
            log.warning("Location lookup failed: %s — falling back to UTC+0", exc)
            return LocationInfo(lat=float("nan"), lon=float("nan"), tz_name=None,
                                country_name=None, utc_offset_minutes=0)


# ── Module-level singleton + public API ───────────────────────────────────────

_cache = _LocationCache()


def get_location(truck_x: float, truck_z: float) -> Optional[LocationInfo]:
    """Return LocationInfo for the given ETS2 truck position (cached)."""
    return _cache.get(truck_x, truck_z)


def reset_cache() -> None:
    """Invalidate the position cache (call at game session start)."""
    _cache.reset()
