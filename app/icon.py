"""
app/icon.py – Lighthouse icon generator for ETS2 Light Sync.

Drawn entirely with QPainter — no external image files needed.
An optional status dot (bottom-right corner) indicates running state in the tray.
"""

from pathlib import Path

from PyQt6.QtCore import Qt, QRectF, QSize
from PyQt6.QtGui import QColor, QIcon, QPainter, QPainterPath, QPixmap


def make_icon(indicator_color: str | None = None) -> QIcon:
    """
    Return a lighthouse QIcon.

    Parameters
    ----------
    indicator_color:
        If given, draw a small filled circle in that color at the bottom-right
        (used by the tray to show running/stopped state).
    """
    size = 256
    pixmap = QPixmap(QSize(size, size))
    pixmap.fill(QColor("transparent"))

    p = QPainter(pixmap)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.setPen(Qt.PenStyle.NoPen)

    _draw_lighthouse(p, size)

    if indicator_color:
        _draw_dot(p, size, indicator_color)

    p.end()
    return QIcon(pixmap)


def save_ico(path: str | Path) -> bool:
    """Save the lighthouse as app/icon.ico for PyInstaller.  Returns True on success."""
    icon = make_icon()
    pixmap = icon.pixmap(QSize(256, 256))
    ok = pixmap.save(str(path), "ICO")
    return ok


# ── Drawing helpers ───────────────────────────────────────────────────────────

def _draw_lighthouse(p: QPainter, s: int) -> None:
    cx = s / 2.0

    # ── Light beam (soft yellow wedge, behind everything) ─────────────────
    beam = QPainterPath()
    beam.moveTo(cx, s * 0.20)
    beam.lineTo(s * 0.01, s * 0.01)
    beam.lineTo(s * 0.38, s * 0.01)
    beam.closeSubpath()
    p.setBrush(QColor(255, 220, 80, 55))
    p.drawPath(beam)

    # ── Base (wide rounded rectangle) ─────────────────────────────────────
    p.setBrush(QColor("#78909C"))
    p.drawRoundedRect(QRectF(s * 0.17, s * 0.83, s * 0.66, s * 0.13), s * 0.02, s * 0.02)

    # ── Tower body (white trapezoid) ──────────────────────────────────────
    bw = s * 0.25   # bottom half-width
    tw = s * 0.155  # top half-width
    ty = s * 0.29   # top y
    by = s * 0.83   # bottom y

    tower = QPainterPath()
    tower.moveTo(cx - bw, by)
    tower.lineTo(cx + bw, by)
    tower.lineTo(cx + tw, ty)
    tower.lineTo(cx - tw, ty)
    tower.closeSubpath()

    p.setBrush(QColor("#F5F5F5"))
    p.drawPath(tower)

    # Red stripes, clipped to the tower shape
    p.save()
    p.setClipPath(tower)
    p.setBrush(QColor("#C0392B"))
    stripe_h = s * 0.062
    for stripe_y in [s * 0.455, s * 0.605, s * 0.725]:
        p.drawRect(QRectF(0, stripe_y, s, stripe_h))
    p.restore()

    # ── Light room (amber rectangle) ──────────────────────────────────────
    lw = s * 0.215
    lh = s * 0.082
    p.setBrush(QColor("#F9A825"))
    p.drawRect(QRectF(cx - lw / 2, ty - lh, lw, lh))

    # Vertical dividers on the glass
    p.setBrush(QColor("#E65100"))
    dw = s * 0.008
    for dx in [cx - lw * 0.25, cx, cx + lw * 0.25]:
        p.drawRect(QRectF(dx - dw / 2, ty - lh, dw, lh))

    # ── Cap (dark triangle) ───────────────────────────────────────────────
    cap = QPainterPath()
    cap.moveTo(cx - s * 0.125, ty - lh)
    cap.lineTo(cx + s * 0.125, ty - lh)
    cap.lineTo(cx, ty - lh - s * 0.10)
    cap.closeSubpath()
    p.setBrush(QColor("#263238"))
    p.drawPath(cap)

    # ── Door (small dark arch at base of tower) ───────────────────────────
    dw2 = s * 0.065
    dh = s * 0.09
    dx2 = cx - dw2 / 2
    dy2 = by - dh
    p.setBrush(QColor("#37474F"))
    p.drawRoundedRect(QRectF(dx2, dy2, dw2, dh), dw2 / 2, dw2 / 2)


def _draw_dot(p: QPainter, s: int, color: str) -> None:
    r = s * 0.13
    x = s - r * 2.1
    y = s - r * 2.1
    # White border
    p.setBrush(QColor("white"))
    p.drawEllipse(QRectF(x - r * 0.2, y - r * 0.2, r * 2.4, r * 2.4))
    # Colored fill
    p.setBrush(QColor(color))
    p.drawEllipse(QRectF(x, y, r * 2, r * 2))
