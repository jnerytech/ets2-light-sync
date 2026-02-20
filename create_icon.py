"""
create_icon.py – Generate app/icon.ico for PyInstaller.

Run once before building the exe:
    .\.venv\Scripts\python.exe create_icon.py
"""

import sys
from pathlib import Path

from PyQt6.QtWidgets import QApplication

from app.icon import save_ico

app = QApplication(sys.argv)

out = Path("app/icon.ico")
ok = save_ico(out)
if ok:
    print(f"Icon saved to {out}")
else:
    print("Failed to save icon (ICO codec unavailable?)", file=sys.stderr)
    sys.exit(1)
