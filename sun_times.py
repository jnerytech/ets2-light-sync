"""
sun_times.py – Generate a dynamic light curve from real astronomical sun events.

Uses the `astral` library (pure-math, no internet required at runtime) to
compute today's sunrise, noon, sunset, and civil twilight for a given
latitude/longitude and IANA timezone.

The resulting curve is a list of (minutes_since_midnight, brightness, kelvin)
tuples compatible with light_curve.calculate_light().  All times are expressed
in the truck's LOCAL timezone so that calculate_light() can be called with
game_time directly.

Caching: the curve is recomputed only when the rounded position changes by
more than ~0.5 degrees or when the date changes.
"""

import datetime
import logging
import math
from typing import Optional
from zoneinfo import ZoneInfo

log = logging.getLogger(__name__)


# ── Sun cache ─────────────────────────────────────────────────────────────────

class _SunCache:
    """Computes and caches astronomical light curves keyed by (lat, lon, date)."""

    def __init__(self) -> None:
        self._key: tuple | None = None
        self._curve: list[tuple[int, int, int]] | None = None

    def get(
        self,
        lat: float,
        lon: float,
        tz_name: str,
        date: Optional[datetime.date] = None,
    ) -> Optional[list[tuple[int, int, int]]]:
        """Return a light-curve for the given location and date, or None on error."""
        if math.isnan(lat) or math.isnan(lon):
            return None

        try:
            from astral import LocationInfo
            from astral.sun import sun as astral_sun
        except ImportError:
            log.warning("astral library not installed — using static light curve")
            return None

        try:
            tz = ZoneInfo(tz_name)
            if date is None:
                date = datetime.datetime.now(tz).date()

            key = (round(lat, 1), round(lon, 1), date.isoformat())
            if key == self._key:
                return self._curve

            location = LocationInfo(latitude=lat, longitude=lon)
            s = astral_sun(location.observer, date=date, tzinfo=tz)

            def _min(dt: datetime.datetime) -> int:
                local = dt.astimezone(tz)
                return local.hour * 60 + local.minute

            dawn    = _min(s["dawn"])
            sunrise = _min(s["sunrise"])
            noon    = _min(s["noon"])
            sunset  = _min(s["sunset"])
            dusk    = _min(s["dusk"])

            curve: list[tuple[int, int, int]] = sorted([
                (0,                          0,   2700),  # midnight — off
                (max(dawn - 15, 1),          0,   2700),  # last dark before civil dawn
                (dawn,                       5,   2000),  # civil dawn — faint amber
                (sunrise,                  255,   5500),  # sunrise — full day
                (noon,                     255,   6000),  # solar noon — peak cool white
                (sunset,                   255,   5200),  # sunset — still full brightness
                (min(sunset + 30, 1430),    20,   2800),  # 30 min after sunset — rapid dim
                (min(dusk + 20,   1435),     0,   2700),  # after civil dusk — off
                (1440,                       0,   2700),  # midnight wrap
            ])

            log.debug(
                "Sun curve for %.2f°N %.2f°E (%s) on %s: "
                "dawn=%02d:%02d sunrise=%02d:%02d noon=%02d:%02d "
                "sunset=%02d:%02d dusk=%02d:%02d",
                lat, lon, tz_name, date,
                dawn // 60, dawn % 60, sunrise // 60, sunrise % 60,
                noon // 60, noon % 60, sunset // 60, sunset % 60,
                dusk // 60, dusk % 60,
            )

            self._key = key
            self._curve = curve
            return curve

        except Exception as exc:
            log.debug("Sun curve unavailable (lat=%.2f lon=%.2f): %s", lat, lon, exc)
            self._key = (round(lat, 1), round(lon, 1),
                         (date or datetime.date.today()).isoformat())
            self._curve = None
            return None

    def reset(self) -> None:
        """Invalidate the cache."""
        self._key = None
        self._curve = None


# ── Module-level singleton + public API ───────────────────────────────────────

_cache = _SunCache()


def get_sun_curve(
    lat: float,
    lon: float,
    tz_name: str,
    date: Optional[datetime.date] = None,
) -> Optional[list[tuple[int, int, int]]]:
    """Return dynamic light-curve waypoints based on today's astronomical events.

    Parameters
    ----------
    lat, lon:
        Real-world latitude/longitude of the truck (decimal degrees).
    tz_name:
        IANA timezone name for the truck's position (e.g. ``"Europe/Berlin"``).
    date:
        Date to compute sun events for.  Defaults to today in the truck's local
        timezone.  Pass an explicit value in tests / simulation.

    Returns
    -------
    list of (minute, brightness, kelvin) tuples, or ``None`` on error.
    ``None`` means the caller should fall back to the static built-in curve.
    """
    return _cache.get(lat, lon, tz_name, date)


def reset_cache() -> None:
    """Invalidate the sun-curve cache (call at session start)."""
    _cache.reset()
