"""
light_curve.py – Day/night cycle light settings for ETS2.

Converts an in-game time-of-day (0–1439 minutes) into bulb brightness and
colour temperature using a multi-waypoint curve with cosine easing between
every segment.

Curve waypoints  (all times in game-minutes since midnight):
  00:00  Midnight    →   8 br   2700 K   dark neutral
  05:30  Night end   →   8 br   2700 K   dark neutral
  06:30  Sunrise     →  14 br   2100 K   warm amber burst
  07:30  Morning     →  70 br   3000 K   soft warm light
  09:00  Late morn.  → 220 br   4500 K   warming to day
  10:30  Full day    → 255 br   5800 K   cool bright
  14:30  Midday      → 255 br   6000 K   peak cool white
  16:30  Afternoon   → 245 br   5000 K   slight shift
  17:30  Golden hour → 210 br   3400 K   amber/warm
  18:00  Sunset      → 160 br   2600 K   deep amber
  19:00  Dusk        →  18 br   2500 K   rapidly darkening
  20:30  Night       →   8 br   2700 K   dark neutral
  24:00  Midnight    →   8 br   2700 K   (wraps to start)
"""

import math

# ── Waypoints ─────────────────────────────────────────────────────────────────
# Each entry: (minutes_since_midnight, brightness 0–255, colour_temp_kelvin)
_CURVE: list[tuple[int, int, int]] = [
    (    0,   0,  2700),  # 00:00  midnight       — off
    (  330,   0,  2700),  # 05:30  night end      — off
    (  390,  14,  2100),  # 06:30  sunrise — warm amber, fades in
    (  450,  70,  3000),  # 07:30  early morning
    (  540, 220,  4500),  # 09:00  morning
    (  630, 255,  5800),  # 10:30  full day
    (  870, 255,  6000),  # 14:30  midday peak (cool)
    (  990, 245,  5000),  # 16:30  afternoon
    ( 1050, 210,  3400),  # 17:30  golden hour
    ( 1080, 160,  2600),  # 18:00  sunset amber
    ( 1140,   0,  2500),  # 19:00  dusk — off
    ( 1440,   0,  2700),  # 24:00  midnight (= start)
]


def _smooth(t: float) -> float:
    """Cosine ease-in/out: maps t ∈ [0, 1] → [0, 1]."""
    return (1.0 - math.cos(t * math.pi)) / 2.0


def calculate_light(game_time_minutes: int) -> tuple[int, int]:
    """Return ``(brightness, colour_temp_kelvin)`` for the given game time.

    Parameters
    ----------
    game_time_minutes:
        Minutes since midnight, range 0–1439 (normalised via modulo).

    Returns
    -------
    tuple[int, int]
        ``brightness`` in 0–255 and ``colour_temp_kelvin`` in Kelvin.
    """
    t = game_time_minutes % 1440

    for i in range(len(_CURVE) - 1):
        t0, b0, k0 = _CURVE[i]
        t1, b1, k1 = _CURVE[i + 1]
        if t0 <= t < t1:
            p = _smooth((t - t0) / (t1 - t0))
            return round(b0 + p * (b1 - b0)), round(k0 + p * (k1 - k0))

    return _CURVE[0][1], _CURVE[0][2]
