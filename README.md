## GUI desktop app

```powershell
# Install dependencies (includes PyQt6)
.\.venv\Scripts\python.exe -m pip install -r requirements.txt

# Run the GUI
.\.venv\Scripts\python.exe main_gui.py
```

On first launch, open **Settings** (⚙) and fill in your HA URL, token, and entity ID.
The config is saved to `config/settings.json` next to the script (or exe).

### Build a standalone exe

```powershell
.\.venv\Scripts\python.exe -m PyInstaller --onedir --windowed --name ETS2LightSync main_gui.py
# Output: dist\ETS2LightSync\ETS2LightSync.exe
```

---

## Console mode (legacy)

```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
# or without activation:
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe main.py
```

## Windows: create and edit `.env`

PowerShell:

```powershell
Copy-Item .env.example .env
notepad .env
```

Command Prompt (CMD):

```cmd
copy .env.example .env
notepad .env
```

If `.env.example` does not exist, create `.env` directly:

```powershell
ni .env
notepad .env
```

## Windows: deactivate `.venv`

PowerShell:

```powershell
deactivate
```

Command Prompt (CMD):

```cmd
deactivate
```
