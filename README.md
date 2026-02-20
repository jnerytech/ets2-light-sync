python3 -m venv .venv
source .venv/bin/activate
deactivate
pip install -r requirements.txt
python test_ha_light.py

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
