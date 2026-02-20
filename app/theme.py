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
    p.setColor(QPalette.ColorRole.Window,          QColor(228, 228, 228))
    p.setColor(QPalette.ColorRole.WindowText,      QColor(10, 10, 10))
    p.setColor(QPalette.ColorRole.Base,            QColor(255, 255, 255))
    p.setColor(QPalette.ColorRole.AlternateBase,   QColor(238, 238, 238))
    p.setColor(QPalette.ColorRole.ToolTipBase,     QColor(255, 255, 220))
    p.setColor(QPalette.ColorRole.ToolTipText,     QColor(10, 10, 10))
    p.setColor(QPalette.ColorRole.Text,            QColor(10, 10, 10))
    p.setColor(QPalette.ColorRole.Button,          QColor(200, 200, 200))
    p.setColor(QPalette.ColorRole.ButtonText,      QColor(10, 10, 10))
    p.setColor(QPalette.ColorRole.BrightText,      Qt.GlobalColor.red)
    p.setColor(QPalette.ColorRole.Link,            QColor(0, 80, 180))
    p.setColor(QPalette.ColorRole.Highlight,       QColor(0, 100, 200))
    p.setColor(QPalette.ColorRole.HighlightedText, Qt.GlobalColor.white)
    p.setColor(QPalette.ColorRole.Mid,             QColor(160, 160, 160))
    p.setColor(QPalette.ColorRole.Dark,            QColor(130, 130, 130))
    p.setColor(QPalette.ColorRole.Shadow,          QColor(80, 80, 80))
    p.setColor(QPalette.ColorGroup.Disabled,
               QPalette.ColorRole.Text,       QColor(140, 140, 140))
    p.setColor(QPalette.ColorGroup.Disabled,
               QPalette.ColorRole.ButtonText, QColor(140, 140, 140))
    return p
