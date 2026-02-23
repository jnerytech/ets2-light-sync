"""
light_curve.py – Day/night cycle light settings for ETS2.

Converts an in-game time-of-day (0–1439 minutes) into bulb brightness and
colour temperature using a multi-waypoint curve with cosine easing between
every segment.

Curve waypoints  (all times in game-minutes since midnight):
  00:00  Midnight    →   0 br   2700 K   off
  04:30  Night end   →   0 br   2700 K   off — start of slow rise
  05:30  Dawn        →  25 br   2200 K   warm amber, slowly brightening
  06:00  Full day    → 255 br   5500 K   clear bright
  12:00  Midday      → 255 br   6000 K   peak cool white
  18:00  Sunset      → 255 br   5200 K   begin darkening
  19:00  Dusk        →  50 br   2800 K   rapidly dimming
  20:00  Night       →   0 br   2700 K   off
  24:00  Midnight    →   0 br   2700 K   (wraps to start)
"""

import math

# ── Waypoints ─────────────────────────────────────────────────────────────────
# Each entry: (minutes_since_midnight, brightness 0–255, colour_temp_kelvin)
_CURVE: list[tuple[int, int, int]] = [
    (    0,   0,  2700),  # 00:00  midnight       — off
    (  270,   0,  2700),  # 04:30  night end      — off, start rising
    (  330,  25,  2200),  # 05:30  dawn — warm amber, slowly brightening
    (  360, 255,  5500),  # 06:00  full day — clear bright
    (  720, 255,  6000),  # 12:00  midday peak (cool)
    ( 1080, 255,  5200),  # 18:00  start darkening
    ( 1140,  50,  2800),  # 19:00  dusk — dimming fast
    ( 1200,   0,  2700),  # 20:00  off
    ( 1440,   0,  2700),  # 24:00  midnight (= start)
]


def _smooth(t: float) -> float:
    """Cosine ease-in/out: maps t ∈ [0, 1] → [0, 1]."""
    return (1.0 - math.cos(t * math.pi)) / 2.0


def calculate_light(
    game_time_minutes: int,
    curve: list | None = None,
) -> tuple[int, int]:
    """Return ``(brightness, colour_temp_kelvin)`` for the given game time.

    Parameters
    ----------
    game_time_minutes:
        Minutes since midnight, range 0–1439 (normalised via modulo).
    curve:
        Optional list of ``(minutes, brightness, kelvin)`` waypoints.
        Defaults to the built-in ``_CURVE`` when ``None``.

    Returns
    -------
    tuple[int, int]
        ``brightness`` in 0–255 and ``colour_temp_kelvin`` in Kelvin.
    """
    c = _CURVE if curve is None else curve
    t = game_time_minutes % 1440

    for i in range(len(c) - 1):
        t0, b0, k0 = c[i]
        t1, b1, k1 = c[i + 1]
        if t0 <= t < t1:
            p = _smooth((t - t0) / (t1 - t0))
            return round(b0 + p * (b1 - b0)), round(k0 + p * (k1 - k0))

    return c[0][1], c[0][2]
