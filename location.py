"""
location.py – ETS2 world coordinates → real-world LocationInfo.

Converts truck world-space coordinates (X=East, Z=South, game unit ≈ 1 m at
1:19 map scale) into a real-world latitude/longitude, then determines:
  - IANA timezone name (via offline timezonefinder)
  - Country display name (via static data/ets2_countries.json)
  - UTC offset in minutes (via zoneinfo, including DST)

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
#
# See data/ets2_calibration.json for the full reference table.

_REF_X   = -31600.0   # Paris ETS2 X (East)
_REF_Z   = -62000.0   # Paris ETS2 Z (South)
_REF_LAT =  48.8566   # Paris real latitude
_REF_LON =   2.3522   # Paris real longitude

# scale_lon = Δreal_lon / Δets2_x
_SCALE_LON = (13.4050 - 2.3522) / (17400.0 - (-31600.0))   # ≈ 0.00022548 deg/unit

# scale_lat: in the ETS2 world map, less-negative Z = further north = larger lat.
_SCALE_LAT = (52.5200 - 48.8566) / (-39200.0 - (-62000.0))  # ≈ 0.00016074 deg/unit

# ── Cache settings ─────────────────────────────────────────────────────────────
# Re-query timezone only when truck moves more than this many game units (~5 km).
_CACHE_THRESHOLD_UNITS = 5000.0

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


# ── Module-level cache ─────────────────────────────────────────────────────────
_cached_x:    Optional[float]        = None
_cached_z:    Optional[float]        = None
_cached_info: Optional[LocationInfo] = None


def ets2_to_latlon(x: float, z: float) -> tuple[float, float]:
    """Convert ETS2 world coordinates to real-world (latitude, longitude).

    Parameters
    ----------
    x:
        World East coordinate (game units).
    z:
        World Z coordinate (game units).  In the ETS2 Europe map, less-negative
        Z corresponds to further north (larger latitude).

    Returns
    -------
    tuple[float, float]
        (latitude, longitude) in decimal degrees.
    """
    lat = _REF_LAT + (z - _REF_Z) * _SCALE_LAT   # less-negative Z = further north
    lon = _REF_LON + (x - _REF_X) * _SCALE_LON
    return lat, lon


def get_country_name(tz_name: str) -> Optional[str]:
    """Return country display name for a given IANA timezone name, or None."""
    entry = _COUNTRIES.get(tz_name)
    return entry["name"] if entry else None


def get_location(
    truck_x: float,
    truck_z: float,
) -> Optional[LocationInfo]:
    """Return full LocationInfo for the given ETS2 truck position.

    Uses a cached result when the truck has moved less than
    _CACHE_THRESHOLD_UNITS since the last successful lookup.

    Returns ``None`` when:
    - Coordinates are NaN (game not running or sim mode)
    - Any exception occurs during lookup

    Falls back to utc_offset_minutes=0, country_name=None when the timezone
    cannot be determined (open sea, out-of-range coords).

    Parameters
    ----------
    truck_x:
        ETS2 World East coordinate (game units).
    truck_z:
        ETS2 World South coordinate (game units).

    Returns
    -------
    LocationInfo or None
    """
    global _cached_x, _cached_z, _cached_info

    # Guard: invalid coordinates (NaN = game not running / sim mode)
    if math.isnan(truck_x) or math.isnan(truck_z):
        return None

    # Cache hit: skip re-query when truck hasn't moved significantly
    if _cached_x is not None and _cached_z is not None:
        dist = math.hypot(truck_x - _cached_x, truck_z - _cached_z)
        if dist < _CACHE_THRESHOLD_UNITS:
            return _cached_info

    # Convert and look up timezone
    try:
        lat, lon = ets2_to_latlon(truck_x, truck_z)

        # Clamp to valid geographic range before querying
        lat = max(-90.0, min(90.0, lat))
        lon = max(-180.0, min(180.0, lon))

        from timezonefinder import TimezoneFinder
        tz_name = TimezoneFinder().timezone_at(lat=lat, lng=lon)

        if tz_name is None:
            log.debug(
                "No timezone found for lat=%.4f lon=%.4f — using UTC+0", lat, lon
            )
            info = LocationInfo(
                lat=lat, lon=lon,
                tz_name=None, country_name=None,
                utc_offset_minutes=0,
            )
            _cached_x, _cached_z, _cached_info = truck_x, truck_z, info
            return info

        # Resolve current UTC offset (includes DST) via zoneinfo
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

        info = LocationInfo(
            lat=lat, lon=lon,
            tz_name=tz_name, country_name=country_name,
            utc_offset_minutes=offset_minutes,
        )
        _cached_x, _cached_z, _cached_info = truck_x, truck_z, info
        return info

    except Exception as exc:
        log.warning("Location lookup failed: %s — falling back to UTC+0", exc)
        # Cache the position anyway to avoid hammering on repeated failures
        info = LocationInfo(
            lat=float("nan"), lon=float("nan"),
            tz_name=None, country_name=None,
            utc_offset_minutes=0,
        )
        _cached_x, _cached_z, _cached_info = truck_x, truck_z, info
        return info


def reset_cache() -> None:
    """Invalidate the position cache.

    Call when starting a new game session so the first poll always
    performs a fresh location lookup.
    """
    global _cached_x, _cached_z, _cached_info
    _cached_x = None
    _cached_z = None
    _cached_info = None
