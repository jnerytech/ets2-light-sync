"""Tests for app/web_server.py — REST API endpoints and AppState integration."""

import pytest
from app.state import AppState
from app.web_server import WebServer, _local_ip


@pytest.fixture()
def state() -> AppState:
    return AppState()


@pytest.fixture()
def client(state: AppState):
    """Flask test client (no real thread started)."""
    server = WebServer(state, port=0)   # port=0 is unused in test client
    server._app.config["TESTING"] = True
    return server._app.test_client(), state


# ── GET / ─────────────────────────────────────────────────────────────────────

def test_dashboard_returns_200(client):
    c, _ = client
    r = c.get("/")
    assert r.status_code == 200

def test_dashboard_is_html(client):
    c, _ = client
    r = c.get("/")
    assert b"<!DOCTYPE html>" in r.data
    assert b"ETS2 Light Sync" in r.data

def test_dashboard_has_api_js(client):
    c, _ = client
    r = c.get("/")
    assert b"/api/status" in r.data


# ── GET /api/status ───────────────────────────────────────────────────────────

def test_status_returns_json(client):
    c, _ = client
    r = c.get("/api/status")
    assert r.status_code == 200
    assert r.content_type.startswith("application/json")

def test_status_initial_values(client):
    c, _ = client
    d = c.get("/api/status").get_json()
    assert d["status"] == "stopped"
    assert d["game_time"] == "00:00"
    assert d["brightness"] == 0

def test_status_reflects_state_update(client):
    c, state = client
    state.update(status="connected", brightness=200, kelvin=5000,
                 game_time=720, game_day=3, country="Germany", tz_name="Europe/Berlin")
    d = c.get("/api/status").get_json()
    assert d["status"] == "connected"
    assert d["brightness"] == 200
    assert d["kelvin"] == 5000
    assert d["game_time"] == "12:00"
    assert d["game_day"] == 3
    assert d["country"] == "Germany"
    assert d["tz_name"] == "Europe/Berlin"

def test_status_game_time_format(client):
    c, state = client
    state.update(game_time=65)   # 1 h 5 min → "01:05"
    d = c.get("/api/status").get_json()
    assert d["game_time"] == "01:05"

def test_status_missing_optional_fields_use_fallback(client):
    c, state = client
    state.update(country=None, tz_name=None)
    d = c.get("/api/status").get_json()
    assert d["country"] == "—"
    assert d["tz_name"] == "UTC"


# ── GET /api/logs ─────────────────────────────────────────────────────────────

def test_logs_returns_list(client):
    c, _ = client
    d = c.get("/api/logs").get_json()
    assert "logs" in d
    assert isinstance(d["logs"], list)

def test_logs_reflects_state(client):
    c, state = client
    state.add_log("line one")
    state.add_log("line two")
    d = c.get("/api/logs").get_json()
    assert "line one" in d["logs"]
    assert "line two" in d["logs"]

def test_logs_limited_to_50(client):
    c, state = client
    for i in range(80):
        state.add_log(f"log {i}")
    d = c.get("/api/logs").get_json()
    assert len(d["logs"]) <= 50


# ── POST /api/start ───────────────────────────────────────────────────────────

def test_start_queues_pending_action(client):
    c, state = client
    r = c.post("/api/start")
    assert r.status_code == 200
    assert r.get_json()["queued"] is True
    assert state.pop_pending() == "start"

def test_start_response_is_json(client):
    c, _ = client
    r = c.post("/api/start")
    assert r.content_type.startswith("application/json")


# ── POST /api/stop ────────────────────────────────────────────────────────────

def test_stop_queues_pending_action(client):
    c, state = client
    r = c.post("/api/stop")
    assert r.status_code == 200
    assert state.pop_pending() == "stop"

def test_start_then_stop_order_preserved(client):
    c, state = client
    c.post("/api/start")
    c.post("/api/stop")
    assert state.pop_pending() == "start"
    assert state.pop_pending() == "stop"
    assert state.pop_pending() is None


# ── _local_ip ─────────────────────────────────────────────────────────────────

def test_local_ip_returns_string():
    ip = _local_ip()
    assert isinstance(ip, str)
    assert len(ip) > 0

def test_local_ip_looks_like_ip():
    ip = _local_ip()
    parts = ip.split(".")
    assert len(parts) == 4
    assert all(p.isdigit() for p in parts)


# ── AppState ──────────────────────────────────────────────────────────────────

def test_state_update_atomic(state):
    state.update(brightness=100, kelvin=3000, status="connected")
    assert state.brightness == 100
    assert state.kelvin == 3000
    assert state.status == "connected"

def test_state_add_log_max_lines(state):
    state._max_logs = 5
    for i in range(10):
        state.add_log(f"line {i}")
    assert len(state.get_logs()) == 5

def test_state_pop_pending_empty(state):
    assert state.pop_pending() is None

def test_state_request_start_stop(state):
    state.request_start()
    state.request_stop()
    assert state.pop_pending() == "start"
    assert state.pop_pending() == "stop"
    assert state.pop_pending() is None
