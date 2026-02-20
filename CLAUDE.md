# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

**ETS2 Light Sync** is a Python application that reads Euro Truck Simulator 2 game time from Windows shared memory and controls a Home Assistant smart light to simulate a day/night cycle.

## Development Commands

```powershell
# Install dependencies
pip install -r requirements.txt

# Run headless mode (config via .env)
python main.py

# Run GUI mode (config via config/settings.json)
python main_gui.py

# Manual integration tests
python test_ha_light.py      # Test Home Assistant API connectivity
python test_telemetry.py     # Poll ETS2 telemetry and print light values

# Generate icon (run before building)
python create_icon.py

# Build standalone exe (PowerShell)
./build.ps1
# Equivalent: python -m PyInstaller --onedir --windowed --name ETS2LightSync --icon app\icon.ico main_gui.py

# Release new version (auto-increments patch, tags, triggers CI)
./release.ps1
# Or with explicit version: ./release.ps1 -Version 0.1.0
```

There are no automated tests — `test_ha_light.py` and `test_telemetry.py` are manual integration scripts.

## Architecture

Two entry points with different config sources:
- **`main.py`** — headless, polls in main thread, reads config from `.env`
- **`main_gui.py`** → **`app/sync_worker.py`** (QThread) — GUI app, reads config from `config/settings.json`

Core pipeline (shared between both modes):

```
ETS2 shared memory ("Local\SCSTelemetry")
  → telemetry.py          # Returns Telemetry(game_time: 0-1439 min, paused: bool)
  → light_curve.py        # Maps game_time to (brightness: 0-255, color_temp_k: Kelvin)
                          # Uses 12 waypoints with cosine interpolation
  → ha_client.py          # POST /api/services/light/turn_on to Home Assistant REST API
```

On any exit (normal, crash, SIGTERM, window close), `reset_to_default()` in `ha_client.py` restores the light to configured default brightness/color temp.

## Key Files

| File | Purpose |
|------|---------|
| `telemetry.py` | Windows shared memory reader (SCS SDK). No-op on non-Windows. |
| `light_curve.py` | 12-waypoint cosine-eased day/night brightness + color temp curve |
| `ha_client.py` | Home Assistant REST client with graceful error handling |
| `main.py` | Headless orchestrator — poll loop, signal handlers, `.env` config |
| `main_gui.py` | PyQt6 entry point — sets up app, tray, `atexit` reset hook |
| `app/sync_worker.py` | QThread mirroring `main.py` logic for the GUI |
| `app/config.py` | JSON config load/save with atomic writes to `config/settings.json` |
| `app/main_window.py` | Main window: live logs, start/stop, settings, tray integration |
| `app/settings_dialog.py` | Settings form for all configuration parameters |
| `ETS2LightSync.spec` | PyInstaller spec used by `build.ps1` |
| `release.ps1` | Bumps `VERSION`, commits, tags, pushes — triggers GitHub Actions CI |
| `VERSION` | Plain-text version file (e.g. `0.0.6`) |

## Configuration

**GUI mode** (`config/settings.json`, stored next to exe when frozen):

| Key | Default | Description |
|-----|---------|-------------|
| `ha_url` | `http://192.168.3.155:8123` | Home Assistant base URL |
| `ha_token` | *(required)* | HA long-lived access token |
| `entity_id` | `light.luz` | Target light entity ID |
| `poll_interval` | `5` | Seconds between telemetry polls |
| `transition_time` | `5` | HA light fade duration (seconds) |
| `default_brightness` | `255` | Brightness to reset to on exit |
| `default_color_temp_k` | `4000` | Color temp to reset to on exit (Kelvin) |
| `sim_mode` | `false` | Simulate game time without ETS2 running |
| `sim_time_start` | `360` | Sim start time in minutes (360 = 06:00) |
| `sim_time_speed` | `60.0` | Game-minutes per real-second in sim mode |

**Headless mode** uses the same keys as a `.env` file (see `.env.example`).

## Release Process

1. Run `./release.ps1` (PowerShell on Windows)
2. Script increments `VERSION`, commits, creates `vX.X.X` git tag, pushes
3. GitHub Actions (`.github/workflows/build.yml`) triggers on the tag: installs deps, generates icon, builds exe via PyInstaller, zips, creates GitHub Release with the zip attached

See `docs/release.md` for details.
