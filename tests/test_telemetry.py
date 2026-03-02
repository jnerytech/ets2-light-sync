"""Tests for telemetry.py — Telemetry NamedTuple and platform guard."""

import sys
import pytest
from telemetry import Telemetry, get_telemetry


# ── Telemetry NamedTuple ──────────────────────────────────────────────────────

def test_fields_accessible():
    t = Telemetry(game_time=720, game_day=3, paused=False,
                  truck_x=100.0, truck_z=-200.0)
    assert t.game_time == 720
    assert t.game_day == 3
    assert t.paused is False
    assert t.truck_x == 100.0
    assert t.truck_z == -200.0

def test_game_day_derived_from_abs_time():
    time_abs = 5000
    t = Telemetry(
        game_time=time_abs % 1440,
        game_day=time_abs // 1440,
        paused=False, truck_x=0.0, truck_z=0.0,
    )
    assert t.game_day == 3    # 5000 // 1440
    assert t.game_time == 680  # 5000 % 1440

def test_game_day_zero_at_epoch():
    t = Telemetry(game_time=0, game_day=0, paused=False, truck_x=0.0, truck_z=0.0)
    assert t.game_day == 0

def test_paused_flag():
    paused = Telemetry(game_time=100, game_day=0, paused=True,
                       truck_x=0.0, truck_z=0.0)
    running = Telemetry(game_time=100, game_day=0, paused=False,
                        truck_x=0.0, truck_z=0.0)
    assert paused.paused is True
    assert running.paused is False

def test_nan_coordinates_allowed():
    import math
    t = Telemetry(game_time=0, game_day=0, paused=False,
                  truck_x=float("nan"), truck_z=float("nan"))
    assert math.isnan(t.truck_x)
    assert math.isnan(t.truck_z)


# ── get_telemetry — platform guard ────────────────────────────────────────────

def test_returns_none_on_non_windows(monkeypatch):
    monkeypatch.setattr(sys, "platform", "linux")
    assert get_telemetry() is None

def test_returns_none_on_darwin(monkeypatch):
    monkeypatch.setattr(sys, "platform", "darwin")
    assert get_telemetry() is None
