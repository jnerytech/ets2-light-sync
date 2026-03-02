"""
main_gui.py – PyQt6 entry point for ETS2 Light Sync.

Run with:
    python main_gui.py

Or build a standalone exe:
    pyinstaller --onedir --windowed --name ETS2LightSync --icon app/icon.ico main_gui.py
"""

import atexit
import signal
import sys

from PyQt6.QtCore import QTimer
from PyQt6.QtWidgets import QApplication

from app import config, theme
from app.icon import make_icon
from app.main_window import MainWindow

# Tell Windows this is its own app (not python.exe) so the correct icon
# appears in taskbar groups and toast notifications.
if sys.platform == "win32":
    import ctypes
    ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("ETS2LightSync")


def _reset_light_on_exit() -> None:
    """Emergency reset — runs on any interpreter shutdown (crash, exception, SIGTERM).
    Creates a fresh HA client from saved config and calls reset_to_default().
    Silently ignored if config is missing or the network is unreachable.
    """
    try:
        cfg = config.load()
        if not cfg.get("ha_token"):
            return
        from ha_client import HomeAssistantClient
        HomeAssistantClient(
            url=str(cfg["ha_url"]),
            token=str(cfg["ha_token"]),
            entity_id=str(cfg["entity_id"]),
            transition=float(cfg["transition_time"]),
            default_brightness=int(cfg["default_brightness"]),
            default_color_temp_k=int(cfg["default_color_temp_k"]),
        ).reset_to_default()
    except Exception:
        pass


atexit.register(_reset_light_on_exit)


def main() -> None:
    app = QApplication(sys.argv)
    app.setApplicationName("ETS2 Light Sync")
    app.setWindowIcon(make_icon())        # taskbar, Alt+Tab, title bar
    app.setQuitOnLastWindowClosed(False)  # keep alive in tray

    theme.init()
    theme.apply(config.load().get("theme", "System"))

    window = MainWindow()
    window.show()

    # Let Python process SIGINT/SIGTERM while the Qt event loop is running.
    # A 200 ms timer wakes the loop so pending signals aren't delayed.
    signal.signal(signal.SIGINT,  lambda *_: app.quit())
    signal.signal(signal.SIGTERM, lambda *_: app.quit())
    pulse = QTimer()
    pulse.start(200)
    pulse.timeout.connect(lambda: None)  # type: ignore[misc]

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
