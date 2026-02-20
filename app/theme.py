"""
app/theme.py – Light / Dark / System theme support.

Call init() once after QApplication is created to snapshot the OS palette,
then apply(name) at any time to switch themes.
"""

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor, QPalette
from PyQt6.QtWidgets import QApplication

THEMES = ["System", "Light", "Dark"]

_system_palette: QPalette | None = None


def init() -> None:
    """Snapshot the OS palette before any customisation. Call once at startup."""
    global _system_palette
    app = QApplication.instance()
    if isinstance(app, QApplication):
        _system_palette = QPalette(app.palette())


def apply(name: str) -> None:
    """Apply 'System', 'Light', or 'Dark' theme to the running QApplication."""
    app = QApplication.instance()
    if not isinstance(app, QApplication):
        return
    if name == "Dark":
        app.setPalette(_dark_palette())
    elif name == "Light":
        app.setPalette(_light_palette())
    else:
        if _system_palette is not None:
            app.setPalette(_system_palette)


# ── Palettes ──────────────────────────────────────────────────────────────────

def _dark_palette() -> QPalette:
    p = QPalette()
    p.setColor(QPalette.ColorRole.Window,          QColor(45, 45, 45))
    p.setColor(QPalette.ColorRole.WindowText,      Qt.GlobalColor.white)
    p.setColor(QPalette.ColorRole.Base,            QColor(30, 30, 30))
    p.setColor(QPalette.ColorRole.AlternateBase,   QColor(45, 45, 45))
    p.setColor(QPalette.ColorRole.ToolTipBase,     QColor(30, 30, 30))
    p.setColor(QPalette.ColorRole.ToolTipText,     Qt.GlobalColor.white)
    p.setColor(QPalette.ColorRole.Text,            Qt.GlobalColor.white)
    p.setColor(QPalette.ColorRole.Button,          QColor(55, 55, 55))
    p.setColor(QPalette.ColorRole.ButtonText,      Qt.GlobalColor.white)
    p.setColor(QPalette.ColorRole.BrightText,      Qt.GlobalColor.red)
    p.setColor(QPalette.ColorRole.Link,            QColor(80, 160, 240))
    p.setColor(QPalette.ColorRole.Highlight,       QColor(80, 160, 240))
    p.setColor(QPalette.ColorRole.HighlightedText, QColor(30, 30, 30))
    p.setColor(QPalette.ColorGroup.Disabled,
               QPalette.ColorRole.Text,       QColor(110, 110, 110))
    p.setColor(QPalette.ColorGroup.Disabled,
               QPalette.ColorRole.ButtonText, QColor(110, 110, 110))
    return p


def _light_palette() -> QPalette:
    p = QPalette()
    p.setColor(QPalette.ColorRole.Window,          QColor(240, 240, 240))
    p.setColor(QPalette.ColorRole.WindowText,      Qt.GlobalColor.black)
    p.setColor(QPalette.ColorRole.Base,            Qt.GlobalColor.white)
    p.setColor(QPalette.ColorRole.AlternateBase,   QColor(245, 245, 245))
    p.setColor(QPalette.ColorRole.ToolTipBase,     Qt.GlobalColor.white)
    p.setColor(QPalette.ColorRole.ToolTipText,     Qt.GlobalColor.black)
    p.setColor(QPalette.ColorRole.Text,            Qt.GlobalColor.black)
    p.setColor(QPalette.ColorRole.Button,          QColor(225, 225, 225))
    p.setColor(QPalette.ColorRole.ButtonText,      Qt.GlobalColor.black)
    p.setColor(QPalette.ColorRole.BrightText,      Qt.GlobalColor.red)
    p.setColor(QPalette.ColorRole.Link,            QColor(0, 100, 200))
    p.setColor(QPalette.ColorRole.Highlight,       QColor(0, 120, 215))
    p.setColor(QPalette.ColorRole.HighlightedText, Qt.GlobalColor.white)
    p.setColor(QPalette.ColorGroup.Disabled,
               QPalette.ColorRole.Text,       QColor(160, 160, 160))
    p.setColor(QPalette.ColorGroup.Disabled,
               QPalette.ColorRole.ButtonText, QColor(160, 160, 160))
    return p
