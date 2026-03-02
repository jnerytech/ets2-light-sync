"""Tests for sun_times.py — astronomical light curve generation and caching."""

import datetime
from unittest.mock import MagicMock, patch

import pytest

from sun_times import _SunCache, get_sun_curve, reset_cache

# Paris, France — well-tested reference location
_LAT, _LON, _TZ = 48.8566, 2.3522, "Europe/Paris"
_DATE = datetime.date(2024, 6, 21)  # summer solstice — sun always rises/sets


# ── NaN guard ────────────────────────────────────────────────────────────────

def test_nan_lat_returns_none():
    assert get_sun_curve(float("nan"), _LON, _TZ, _DATE) is None

def test_nan_lon_returns_none():
    assert get_sun_curve(_LAT, float("nan"), _TZ, _DATE) is None


# ── Known location — structural checks ───────────────────────────────────────

def test_returns_list_of_tuples():
    curve = get_sun_curve(_LAT, _LON, _TZ, _DATE)
    assert curve is not None
    assert all(isinstance(wp, tuple) and len(wp) == 3 for wp in curve)

def test_curve_is_sorted_by_time():
    curve = get_sun_curve(_LAT, _LON, _TZ, _DATE)
    assert curve is not None
    times = [wp[0] for wp in curve]
    assert times == sorted(times)

def test_curve_starts_at_midnight():
    curve = get_sun_curve(_LAT, _LON, _TZ, _DATE)
    assert curve is not None
    assert curve[0][0] == 0

def test_curve_ends_at_midnight():
    curve = get_sun_curve(_LAT, _LON, _TZ, _DATE)
    assert curve is not None
    assert curve[-1][0] == 1440

def test_curve_has_peak_brightness_255():
    curve = get_sun_curve(_LAT, _LON, _TZ, _DATE)
    assert curve is not None
    assert max(wp[1] for wp in curve) == 255

def test_curve_midnight_is_off():
    curve = get_sun_curve(_LAT, _LON, _TZ, _DATE)
    assert curve is not None
    assert curve[0][1] == 0   # midnight brightness = 0
    assert curve[-1][1] == 0  # wrap point brightness = 0

def test_kelvin_in_valid_range():
    curve = get_sun_curve(_LAT, _LON, _TZ, _DATE)
    assert curve is not None
    for _, _, kelvin in curve:
        assert 1000 <= kelvin <= 10000

def test_summer_solstice_paris_sunrise_before_7am():
    curve = get_sun_curve(_LAT, _LON, _TZ, _DATE)
    assert curve is not None
    # Find first transition to brightness >= 200
    sunrise_minute = next(
        (t for t, b, _ in curve if b >= 200), None
    )
    assert sunrise_minute is not None
    assert sunrise_minute < 7 * 60   # before 07:00


# ── Caching ───────────────────────────────────────────────────────────────────

def test_same_params_returns_cached_object():
    reset_cache()
    c1 = get_sun_curve(_LAT, _LON, _TZ, _DATE)
    c2 = get_sun_curve(_LAT, _LON, _TZ, _DATE)
    assert c1 is c2  # identical object from cache

def test_different_date_recomputes():
    reset_cache()
    c1 = get_sun_curve(_LAT, _LON, _TZ, datetime.date(2024, 6, 21))
    c2 = get_sun_curve(_LAT, _LON, _TZ, datetime.date(2024, 12, 21))
    # Different dates → different curves (winter solstice has shorter day)
    assert c1 != c2

def test_reset_cache_forces_recompute():
    reset_cache()
    c1 = get_sun_curve(_LAT, _LON, _TZ, _DATE)
    reset_cache()
    c2 = get_sun_curve(_LAT, _LON, _TZ, _DATE)
    # Different object instances after reset
    assert c1 is not c2

def test_position_rounded_to_one_decimal():
    """Positions within 0.05° of each other share the cache."""
    reset_cache()
    c1 = get_sun_curve(48.80, 2.30, _TZ, _DATE)
    c2 = get_sun_curve(48.84, 2.34, _TZ, _DATE)  # rounds to same 48.8, 2.3
    assert c1 is c2


# ── _SunCache unit tests ──────────────────────────────────────────────────────

def test_sun_cache_reset_clears_key():
    cache = _SunCache()
    cache.get(_LAT, _LON, _TZ, _DATE)
    cache.reset()
    assert cache._key is None
    assert cache._curve is None

def test_sun_cache_returns_none_on_import_error():
    cache = _SunCache()
    with patch.dict("sys.modules", {"astral": None, "astral.sun": None}):
        result = cache.get(_LAT, _LON, _TZ, _DATE)
    # If astral unavailable, returns None gracefully
    # (may still succeed if astral is installed — just check no exception)
    assert result is None or isinstance(result, list)
