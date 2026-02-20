python3 -m venv .venv
source .venv/bin/activate
deactivate
pip install -r requirements.txt
python test_ha_light.py

Windows (either activate, or run Python from `.venv` directly):

```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
# or without activation:
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe test_ha_light.py
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
