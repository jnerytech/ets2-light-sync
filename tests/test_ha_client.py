"""Tests for ha_client.py — HomeAssistantClient and _kelvin_to_mireds."""

from unittest.mock import MagicMock, patch

import pytest
import requests

from ha_client import HomeAssistantClient, _kelvin_to_mireds

_URL   = "http://ha.local:8123"
_TOKEN = "test-token-abc"
_ENTITY = "light.test"


def _client(**kwargs) -> HomeAssistantClient:
    defaults = dict(url=_URL, token=_TOKEN, entity_id=_ENTITY,
                    transition=1.0, default_brightness=200,
                    default_color_temp_k=4000)
    return HomeAssistantClient(**{**defaults, **kwargs})


# ── _kelvin_to_mireds ─────────────────────────────────────────────────────────

def test_kelvin_to_mireds_6500():
    assert _kelvin_to_mireds(6500) == 154

def test_kelvin_to_mireds_2700():
    assert _kelvin_to_mireds(2700) == 370

def test_kelvin_to_mireds_round_trip():
    for k in (2000, 3000, 4000, 5000, 6500):
        mireds = _kelvin_to_mireds(k)
        assert mireds == round(1_000_000 / k)


# ── constructor ───────────────────────────────────────────────────────────────

def test_empty_token_raises():
    with pytest.raises(ValueError, match="token"):
        HomeAssistantClient(url=_URL, token="", entity_id=_ENTITY)

def test_trailing_slash_stripped():
    client = _client(url="http://ha.local:8123/")
    assert not client.url.endswith("/")

def test_auth_header_set():
    client = _client()
    assert client._headers["Authorization"] == f"Bearer {_TOKEN}"


# ── set_light ─────────────────────────────────────────────────────────────────

def test_set_light_turn_on_payload():
    client = _client()
    with patch("requests.post") as mock_post:
        mock_post.return_value = MagicMock(status_code=200)
        mock_post.return_value.raise_for_status = MagicMock()
        client.set_light(brightness=200, color_temp_kelvin=4000)

    mock_post.assert_called_once()
    _, kwargs = mock_post.call_args
    payload = kwargs["json"]
    assert payload["entity_id"] == _ENTITY
    assert payload["brightness"] == 200
    assert payload["color_temp"] == _kelvin_to_mireds(4000)
    assert "turn_on" in mock_post.call_args[0][0]

def test_set_light_turn_off_when_brightness_zero():
    client = _client()
    with patch("requests.post") as mock_post:
        mock_post.return_value = MagicMock(status_code=200)
        mock_post.return_value.raise_for_status = MagicMock()
        client.set_light(brightness=0, color_temp_kelvin=2700)

    assert "turn_off" in mock_post.call_args[0][0]
    _, kwargs = mock_post.call_args
    assert "brightness" not in kwargs["json"]

def test_set_light_uses_configured_transition():
    client = _client(transition=3.5)
    with patch("requests.post") as mock_post:
        mock_post.return_value = MagicMock(status_code=200)
        mock_post.return_value.raise_for_status = MagicMock()
        client.set_light(brightness=128, color_temp_kelvin=4000)

    _, kwargs = mock_post.call_args
    assert kwargs["json"]["transition"] == 3.5


# ── reset_to_default ──────────────────────────────────────────────────────────

def test_reset_to_default_payload():
    client = _client(default_brightness=180, default_color_temp_k=3500)
    with patch("requests.post") as mock_post:
        mock_post.return_value = MagicMock(status_code=200)
        mock_post.return_value.raise_for_status = MagicMock()
        client.reset_to_default()

    _, kwargs = mock_post.call_args
    payload = kwargs["json"]
    assert payload["brightness"] == 180
    assert payload["color_temp"] == _kelvin_to_mireds(3500)
    assert "turn_on" in mock_post.call_args[0][0]


# ── network error handling ────────────────────────────────────────────────────

def test_network_error_does_not_raise():
    client = _client()
    with patch("requests.post", side_effect=requests.ConnectionError("refused")):
        client.set_light(200, 4000)   # must not propagate the exception

def test_http_error_does_not_raise():
    client = _client()
    mock_resp = MagicMock()
    mock_resp.raise_for_status.side_effect = requests.HTTPError("500")
    with patch("requests.post", return_value=mock_resp):
        client.set_light(200, 4000)   # must not propagate


# ── from_env ─────────────────────────────────────────────────────────────────

def test_from_env_missing_token_raises(monkeypatch):
    monkeypatch.delenv("HA_TOKEN", raising=False)
    with patch("dotenv.load_dotenv"):  # prevent .env file from overriding env
        with pytest.raises(ValueError, match="HA_TOKEN"):
            HomeAssistantClient.from_env()

def test_from_env_constructs_client(monkeypatch):
    monkeypatch.setenv("HA_TOKEN",           "env-token")
    monkeypatch.setenv("HA_URL",             "http://env.host:8123")
    monkeypatch.setenv("ENTITY_ID",          "light.env")
    monkeypatch.setenv("TRANSITION_TIME",    "2")
    monkeypatch.setenv("DEFAULT_BRIGHTNESS", "128")
    monkeypatch.setenv("DEFAULT_COLOR_TEMP_K", "3000")
    with patch("dotenv.load_dotenv"):  # prevent .env file from overriding env
        client = HomeAssistantClient.from_env()
    assert client.url == "http://env.host:8123"
    assert client.entity_id == "light.env"
    assert client.transition == 2.0
    assert client.default_brightness == 128
    assert client.default_color_temp_k == 3000
