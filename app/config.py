"""
app/config.py – Read/write config/settings.json.

Stored next to the exe when frozen, or at the repo root during development.
Created with defaults on first run if absent.
"""

import json
import sys
from pathlib import Path
from typing import Any

_DEFAULTS: dict[str, Any] = {
    "ha_url": "http://192.168.3.155:8123",
    "ha_token": "",
    "entity_id": "light.luz",
    "poll_interval": 15,
    "transition_time": 1,
    "default_brightness": 255,
    "default_color_temp_k": 4000,
}


def _config_path() -> Path:
    if getattr(sys, "frozen", False):
        base = Path(sys.executable).parent
    else:
        base = Path(__file__).parent.parent
    return base / "config" / "settings.json"


def load() -> dict[str, Any]:
    """Return config dict, merged with defaults for any missing keys."""
    path = _config_path()
    if not path.exists():
        return dict(_DEFAULTS)
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        return {**_DEFAULTS, **data}
    except Exception:
        return dict(_DEFAULTS)


def save(data: dict[str, Any]) -> None:
    """Write config atomically."""
    path = _config_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)
    tmp.replace(path)
