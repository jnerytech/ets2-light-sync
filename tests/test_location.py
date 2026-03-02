"""Tests for location.py — coordinate conversion and location cache."""

import math
from unittest.mock import MagicMock, patch

import pytest

from location import (
    LocationInfo,
    _LocationCache,
    ets2_to_latlon,
    get_country_name,
    get_location,
    reset_cache,
)

# Known ETS2 reference city coordinates (calibration anchors)
_PARIS_X, _PARIS_Z   = -31600.0, -62000.0   # → 48.8566°N, 2.3522°E
_BERLIN_X, _BERLIN_Z =  17400.0, -39200.0   # → 52.52°N,  13.405°E


# ── ets2_to_latlon ────────────────────────────────────────────────────────────

def test_paris_reference():
    lat, lon = ets2_to_latlon(_PARIS_X, _PARIS_Z)
    assert abs(lat - 48.8566) < 0.001
    assert abs(lon -  2.3522) < 0.001

def test_berlin_reference():
    lat, lon = ets2_to_latlon(_BERLIN_X, _BERLIN_Z)
    assert abs(lat - 52.52)  < 0.01
    assert abs(lon - 13.405) < 0.01

def test_east_of_paris_increases_longitude():
    _, lon_paris  = ets2_to_latlon(_PARIS_X,           _PARIS_Z)
    _, lon_east   = ets2_to_latlon(_PARIS_X + 10000,   _PARIS_Z)
    assert lon_east > lon_paris

def test_north_of_paris_increases_latitude():
    # In ETS2: less-negative Z (larger value) = further north
    lat_paris, _ = ets2_to_latlon(_PARIS_X, _PARIS_Z)
    lat_north, _ = ets2_to_latlon(_PARIS_X, _PARIS_Z + 10000)  # closer to zero = north
    assert lat_north > lat_paris


# ── get_location — NaN guard ──────────────────────────────────────────────────

def test_nan_x_returns_none():
    reset_cache()
    assert get_location(float("nan"), _PARIS_Z) is None

def test_nan_z_returns_none():
    reset_cache()
    assert get_location(_PARIS_X, float("nan")) is None

def test_both_nan_returns_none():
    reset_cache()
    assert get_location(float("nan"), float("nan")) is None


# ── _LocationCache — caching behaviour ───────────────────────────────────────

def _make_mock_tf(tz_name: str = "Europe/Paris") -> MagicMock:
    mock = MagicMock()
    mock.timezone_at.return_value = tz_name
    return mock

def test_second_call_within_threshold_uses_cache():
    cache = _LocationCache(threshold_units=5000.0)
    mock_tf = _make_mock_tf()
    with patch("location._TF", mock_tf):
        cache.get(_PARIS_X, _PARIS_Z)
        cache.get(_PARIS_X + 100, _PARIS_Z + 100)  # small move
    assert mock_tf.timezone_at.call_count == 1

def test_large_move_forces_new_lookup():
    cache = _LocationCache(threshold_units=5000.0)
    mock_tf = _make_mock_tf()
    with patch("location._TF", mock_tf):
        cache.get(_PARIS_X, _PARIS_Z)
        cache.get(_BERLIN_X, _BERLIN_Z)  # far away
    assert mock_tf.timezone_at.call_count == 2

def test_reset_forces_new_lookup():
    cache = _LocationCache()
    mock_tf = _make_mock_tf()
    with patch("location._TF", mock_tf):
        cache.get(_PARIS_X, _PARIS_Z)
        cache.reset()
        cache.get(_PARIS_X, _PARIS_Z)
    assert mock_tf.timezone_at.call_count == 2

def test_returns_location_info():
    cache = _LocationCache()
    mock_tf = _make_mock_tf("Europe/Paris")
    with patch("location._TF", mock_tf):
        result = cache.get(_PARIS_X, _PARIS_Z)
    assert isinstance(result, LocationInfo)
    assert result.tz_name == "Europe/Paris"

def test_no_timezone_returns_utc_zero():
    cache = _LocationCache()
    mock_tf = _make_mock_tf()
    mock_tf.timezone_at.return_value = None
    with patch("location._TF", mock_tf):
        result = cache.get(_PARIS_X, _PARIS_Z)
    assert result is not None
    assert result.tz_name is None
    assert result.utc_offset_minutes == 0

def test_exception_returns_fallback():
    cache = _LocationCache()
    mock_tf = _make_mock_tf()
    mock_tf.timezone_at.side_effect = RuntimeError("boom")
    with patch("location._TF", mock_tf):
        result = cache.get(_PARIS_X, _PARIS_Z)
    assert result is not None
    assert result.tz_name is None

def test_module_reset_cache_clears_singleton():
    """reset_cache() should clear the module-level _cache singleton."""
    mock_tf = _make_mock_tf()
    with patch("location._TF", mock_tf):
        get_location(_PARIS_X, _PARIS_Z)
        reset_cache()
        get_location(_PARIS_X, _PARIS_Z)
    assert mock_tf.timezone_at.call_count == 2
