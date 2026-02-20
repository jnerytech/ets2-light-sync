"""
light_curve.py – Day/night cycle light settings for ETS2.

Converts an in-game time-of-day (0–1439 minutes) into bulb brightness and
color temperature using smooth sinusoidal S-curves for dawn and dusk.

Timeline (all times in game minutes since midnight):
  00:00 – 05:30  Night   →  dim warm light
  05:30 – 07:00  Dawn    →  gradual transition to full daylight  (FR02)
  07:00 – 18:00  Day     →  full brightness, cool white
  18:00 – 20:00  Dusk    →  gradual transition back to night     (FR02)
  20:00 – 24:00  Night   →  dim warm light
"""

import math

# ── Transition boundaries (minutes since midnight) ──────────────────────────
_NIGHT_END_MIN = 5 * 60 + 30   # 05:30 – dawn starts
_DAWN_END_MIN = 7 * 60          # 07:00 – full day
_DUSK_START_MIN = 18 * 60       # 18:00 – dusk starts
_NIGHT_START_MIN = 20 * 60      # 20:00 – full night

# ── Light values ─────────────────────────────────────────────────────────────
NIGHT_BRIGHTNESS = 13       # ~5 % of 255  (bulb stays on, very dim)
DAY_BRIGHTNESS = 255        # 100 %

NIGHT_KELVIN = 2_200        # Very warm amber  (night / pre-dawn)
DAWN_KELVIN = 3_200         # Warm orange      (sunrise colour)
DAY_KELVIN = 5_500          # Cool daylight


def _smooth(t: float) -> float:
    """Cosine-based smooth step: maps t ∈ [0,1] → [0,1] with ease-in/out."""
    return (1.0 - math.cos(t * math.pi)) / 2.0


def calculate_light(game_time_minutes: int) -> tuple[int, int]:
    """Return ``(brightness, color_temp_kelvin)`` for the given game time.

    Parameters
    ----------
    game_time_minutes:
        Minutes since midnight, expected range 0–1439 (values outside are
        normalised via modulo).

    Returns
    -------
    tuple[int, int]
        ``brightness`` in 0–255 and ``color_temp_kelvin`` in Kelvin.
    """
    t = game_time_minutes % 1440

    if _DAWN_END_MIN <= t < _DUSK_START_MIN:
        # ── Full day ──────────────────────────────────────────────────────
        return DAY_BRIGHTNESS, DAY_KELVIN

    if _NIGHT_END_MIN <= t < _DAWN_END_MIN:
        # ── Dawn: night → day ─────────────────────────────────────────────
        p = _smooth((t - _NIGHT_END_MIN) / (_DAWN_END_MIN - _NIGHT_END_MIN))
        brightness = round(NIGHT_BRIGHTNESS + p * (DAY_BRIGHTNESS - NIGHT_BRIGHTNESS))
        kelvin = round(NIGHT_KELVIN + p * (DAY_KELVIN - NIGHT_KELVIN))
        return brightness, kelvin

    if _DUSK_START_MIN <= t < _NIGHT_START_MIN:
        # ── Dusk: day → night ─────────────────────────────────────────────
        p = _smooth((t - _DUSK_START_MIN) / (_NIGHT_START_MIN - _DUSK_START_MIN))
        brightness = round(DAY_BRIGHTNESS - p * (DAY_BRIGHTNESS - NIGHT_BRIGHTNESS))
        kelvin = round(DAY_KELVIN - p * (DAY_KELVIN - NIGHT_KELVIN))
        return brightness, kelvin

    # ── Night (before dawn or after dusk) ───────────────────────────────────
    return NIGHT_BRIGHTNESS, NIGHT_KELVIN
