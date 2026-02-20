"""
main_gui.py – PyQt6 entry point for ETS2 Light Sync.

Run with:
    python main_gui.py

Or build a standalone exe:
    pyinstaller --onedir --windowed --name ETS2LightSync --icon app/icon.ico main_gui.py
"""

import sys

from PyQt6.QtWidgets import QApplication

from app.icon import make_icon
from app.main_window import MainWindow

# Tell Windows this is its own app (not python.exe) so the correct icon
# appears in taskbar groups and toast notifications.
if sys.platform == "win32":
    import ctypes
    ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("ETS2LightSync")


def main() -> None:
    app = QApplication(sys.argv)
    app.setApplicationName("ETS2 Light Sync")
    app.setWindowIcon(make_icon())        # taskbar, Alt+Tab, title bar
    app.setQuitOnLastWindowClosed(False)  # keep alive in tray

    window = MainWindow()
    window.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
