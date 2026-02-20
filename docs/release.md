# Release Process

Releases are fully automated. A single script bumps the version, commits, tags, and pushes — GitHub Actions does the rest.

---

## How to release

```powershell
.\release.ps1
```

This will:
1. Auto-increment the patch version (e.g. `0.0.5` → `0.0.6`)
2. Write the new version to `VERSION`
3. Commit and push to `master`
4. Create and push the `vX.X.X` tag
5. Print the Actions URL

To release a specific version instead of auto-bumping:

```powershell
.\release.ps1 -Version 1.0.0
```

---

## What happens in CI

When a `v*` tag is pushed, the `Build` workflow (`.github/workflows/build.yml`) runs:

| Step | Description |
|------|-------------|
| Checkout | Clones the repo |
| Set up Python | Installs Python 3.11 |
| Install dependencies | `pip install -r requirements.txt` |
| Generate icon | Runs `create_icon.py` |
| Build exe | PyInstaller → `dist\ETS2LightSync\` |
| Zip artifact | `ETS2LightSync.zip` |
| Upload artifact | Stored for 30 days in Actions |
| Create GitHub Release | Publishes release with zip attached and auto-generated notes |

The **Create GitHub Release** step only runs on tag pushes (`refs/tags/v*`). It is skipped on manual (`workflow_dispatch`) runs.

---

## VERSION file

`VERSION` contains the current version as plain text (e.g. `0.0.6`). It is the single source of truth — `release.ps1` reads and writes it automatically.

---

## Requirements

- Git configured with push access to the remote
- PowerShell 5.1+
