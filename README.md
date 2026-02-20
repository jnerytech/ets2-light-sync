# ETS2 Light Sync

Syncs Euro Truck Simulator 2 in-game time to a Home Assistant light, adjusting
brightness and colour temperature through the day/night cycle.

---

## Requirements

- Windows 10/11
- Python 3.11+
- [SCS SDK telemetry plugin](https://github.com/RenCloud/scs-sdk-plugin) installed in ETS2
- A Home Assistant instance with a long-lived access token

---

## 1 — Local development setup

```powershell
# Clone and enter the repo
git clone <repo-url>
cd ets2-light-sync

# Create virtual environment
py -m venv .venv

# Install dependencies
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

---

## 2 — Quick local test (GUI)

```powershell
.\.venv\Scripts\python.exe main_gui.py
```

1. Click **⚙ Settings**, fill in:
   - **HA URL** — e.g. `http://192.168.1.100:8123`
   - **HA Token** — your long-lived access token
   - **Entity ID** — e.g. `light.desk`
2. Click **OK** — config is saved to `config/settings.json`.
3. Click **▶ Start** — the sync loop begins.
4. Close the window to minimise to the system tray; right-click → **Quit** to exit.

---

## 3 — Build a standalone exe

```powershell
.\build.ps1
```

Output: `dist\ETS2LightSync\ETS2LightSync.exe`

To distribute, copy the entire `dist\ETS2LightSync\` folder.
`config\settings.json` is created next to the exe on first run.

---

## Console mode (no GUI)

Uses `.env` for configuration instead of `config/settings.json`.

```powershell
# Create and edit .env
Copy-Item .env.example .env
notepad .env

# Run
.\.venv\Scripts\python.exe main.py
```

---

## Configuration reference

| Key | Default | Description |
|-----|---------|-------------|
| `ha_url` | `http://192.168.3.155:8123` | Home Assistant base URL |
| `ha_token` | *(required)* | Long-lived access token |
| `entity_id` | `light.luz` | Target light entity |
| `poll_interval` | `15` | Seconds between polls |
| `transition_time` | `1` | Light transition in seconds |
| `default_brightness` | `255` | Brightness on reset (0–255) |
| `default_color_temp_k` | `4000` | Colour temp on reset (Kelvin) |
