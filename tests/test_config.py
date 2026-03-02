"""Tests for app/config.py — load, save, defaults."""

import json
from pathlib import Path
from unittest.mock import patch

import pytest

import app.config as config
from app.config import defaults, load, save


# ── defaults() ───────────────────────────────────────────────────────────────

def test_defaults_returns_dict():
    d = defaults()
    assert isinstance(d, dict)

def test_defaults_has_required_keys():
    d = defaults()
    for key in ("ha_url", "ha_token", "entity_id", "poll_interval",
                "transition_time", "default_brightness", "default_color_temp_k",
                "astronomical_lighting"):
        assert key in d, f"Missing key: {key}"

def test_defaults_no_sim_mode():
    d = defaults()
    assert "sim_mode" not in d
    assert "sim_time_start" not in d
    assert "sim_time_speed" not in d

def test_defaults_returns_copy():
    d1 = defaults()
    d2 = defaults()
    d1["ha_url"] = "mutated"
    assert d2["ha_url"] != "mutated"


# ── load() ───────────────────────────────────────────────────────────────────

def test_load_missing_file_returns_defaults(tmp_path):
    missing = tmp_path / "config" / "settings.json"
    with patch("app.config._config_path", return_value=missing):
        cfg = load()
    assert cfg == defaults()

def test_load_merges_with_defaults(tmp_path):
    path = tmp_path / "config" / "settings.json"
    path.parent.mkdir(parents=True)
    path.write_text(json.dumps({"ha_token": "my-token"}), encoding="utf-8")
    with patch("app.config._config_path", return_value=path):
        cfg = load()
    assert cfg["ha_token"] == "my-token"
    assert cfg["ha_url"] == defaults()["ha_url"]  # default applied

def test_load_corrupted_file_returns_defaults(tmp_path):
    path = tmp_path / "config" / "settings.json"
    path.parent.mkdir(parents=True)
    path.write_text("not json!!!", encoding="utf-8")
    with patch("app.config._config_path", return_value=path):
        cfg = load()
    assert cfg == defaults()


# ── save() + load() round-trip ────────────────────────────────────────────────

def test_save_creates_file(tmp_path):
    path = tmp_path / "config" / "settings.json"
    data = {**defaults(), "ha_token": "saved-token"}
    with patch("app.config._config_path", return_value=path):
        save(data)
    assert path.exists()

def test_save_and_reload(tmp_path):
    path = tmp_path / "config" / "settings.json"
    original = {**defaults(), "ha_token": "round-trip-token", "poll_interval": 42}
    with patch("app.config._config_path", return_value=path):
        save(original)
        loaded = load()
    assert loaded["ha_token"] == "round-trip-token"
    assert loaded["poll_interval"] == 42

def test_save_is_atomic(tmp_path):
    """save() writes to a .tmp file first, then replaces — no .tmp left behind."""
    path = tmp_path / "config" / "settings.json"
    with patch("app.config._config_path", return_value=path):
        save(defaults())
    assert not path.with_suffix(".tmp").exists()

def test_save_creates_parent_dirs(tmp_path):
    deep = tmp_path / "a" / "b" / "c" / "settings.json"
    with patch("app.config._config_path", return_value=deep):
        save(defaults())
    assert deep.exists()
