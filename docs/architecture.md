# Architecture

## Overview

ETS2 Light Sync bridges Euro Truck Simulator 2's in-game time to a Home Assistant smart light, creating a real-world day/night cycle that mirrors the game.

```
ETS2 (game)
  └── scs-telemetry.dll (SCS SDK plugin)
        └── Shared Memory
              └── telemetry.py       ← reads game_time
                    └── light_curve.py  ← maps time → brightness + colour temp
                          └── ha_client.py  ← sends REST API command to Home Assistant
                                └── Smart Light (bulb)
```

---

## Modules

### `telemetry.py`
Reads from the SCS SDK shared memory segment exposed by the `scs-telemetry.dll` plugin.
Returns `game_time` (minutes since midnight) and `truck_on` state.

### `light_curve.py`
Maps the game time to brightness and colour temperature using a day/night curve:

| Time | Brightness | Colour Temp |
|------|-----------|-------------|
| Night | Off | — |
| Sunrise | Fades in | Warm (~2700 K) |
| Midday | Full | Cool (~6500 K) |
| Golden hour | Dims | Warm (~3000 K) |
| Sunset | Off | — |

### `ha_client.py`
Sends `POST /api/services/light/turn_on` to the Home Assistant REST API with the computed brightness and colour temperature.
On shutdown it sends a reset command (default brightness + colour temp).

### `main_gui.py`
PyQt6 GUI entry point. Hosts the settings dialog, start/stop control, and system tray icon.
Reads/writes config from `config/settings.json`.

### `main.py`
Headless (console) entry point. Reads config from `.env`.

---

## Data flow

1. Poll loop runs every `poll_interval` seconds (default 5 s)
2. `telemetry.py` reads `game_time` from shared memory
3. `light_curve.py` computes target `brightness` and `color_temp_kelvin`
4. If values changed since last poll, `ha_client.py` sends the command
5. On exit, `ha_client.py` resets the light to defaults

---

## Configuration

Two config paths depending on entry point:

| Entry point | Config source |
|-------------|--------------|
| `main_gui.py` (exe) | `config/settings.json` (GUI settings dialog) |
| `main.py` (console) | `.env` file |

See `README.md` for the full configuration reference.
