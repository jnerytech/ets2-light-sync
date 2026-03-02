"""Tests for light_curve.py — brightness/kelvin interpolation."""

import pytest
from light_curve import DEFAULT_WAYPOINTS, _smooth, calculate_light


# ── _smooth ───────────────────────────────────────────────────────────────────

def test_smooth_zero():
    assert _smooth(0.0) == 0.0

def test_smooth_one():
    assert _smooth(1.0) == 1.0

def test_smooth_half():
    assert _smooth(0.5) == pytest.approx(0.5)

def test_smooth_monotone():
    values = [_smooth(t / 10) for t in range(11)]
    assert values == sorted(values)


# ── DEFAULT_WAYPOINTS shape ───────────────────────────────────────────────────

def test_default_waypoints_not_empty():
    assert len(DEFAULT_WAYPOINTS) >= 3

def test_default_waypoints_starts_at_midnight():
    assert DEFAULT_WAYPOINTS[0][0] == 0

def test_default_waypoints_ends_at_midnight():
    assert DEFAULT_WAYPOINTS[-1][0] == 1440

def test_default_waypoints_sorted():
    times = [wp[0] for wp in DEFAULT_WAYPOINTS]
    assert times == sorted(times)

def test_default_waypoints_brightness_range():
    for _, brightness, _ in DEFAULT_WAYPOINTS:
        assert 0 <= brightness <= 255

def test_default_waypoints_kelvin_range():
    for _, _, kelvin in DEFAULT_WAYPOINTS:
        assert 1000 <= kelvin <= 10000


# ── calculate_light — built-in curve ─────────────────────────────────────────

def test_night_is_off():
    brightness, _ = calculate_light(0)    # midnight
    assert brightness == 0

def test_noon_is_full():
    brightness, kelvin = calculate_light(720)    # 12:00
    assert brightness == 255
    assert kelvin == 6000

def test_wraps_1440_to_midnight():
    b0, k0 = calculate_light(0)
    b1, k1 = calculate_light(1440)
    assert b0 == b1
    assert k0 == k1

def test_modulo_normalization():
    # 1441 min == 1 min
    b_direct, k_direct = calculate_light(1)
    b_wrapped, k_wrapped = calculate_light(1441)
    assert b_direct == b_wrapped
    assert k_direct == k_wrapped

def test_returns_tuple_of_two_ints():
    result = calculate_light(600)
    assert len(result) == 2
    assert all(isinstance(v, int) for v in result)


# ── calculate_light — custom curve ───────────────────────────────────────────

_FLAT_CURVE = [
    (0,    100,  3000),
    (1440, 100,  3000),
]

_RAMP_CURVE = [
    (0,    0,   2700),
    (720,  255, 6000),
    (1440, 0,   2700),
]

def test_custom_flat_curve():
    for minute in (0, 360, 720, 1080, 1439):
        brightness, kelvin = calculate_light(minute, _FLAT_CURVE)
        assert brightness == 100
        assert kelvin == 3000

def test_custom_ramp_midpoint():
    # At t=360 (halfway between 0→720 on the ramp) cosine easing gives 0.5
    brightness, _ = calculate_light(360, _RAMP_CURVE)
    assert 120 <= brightness <= 135  # ~128 with cosine easing

def test_custom_curve_peak():
    brightness, kelvin = calculate_light(720, _RAMP_CURVE)
    assert brightness == 255
    assert kelvin == 6000

def test_none_curve_uses_default():
    b_none, k_none = calculate_light(720, None)
    b_default, k_default = calculate_light(720)
    assert b_none == b_default
    assert k_none == k_default
