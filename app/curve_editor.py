"""app/curve_editor.py – Interactive light-curve editor dialog.

Provides a draggable graph (CurvePreviewWidget) and a waypoint table
(CurveEditorDialog) for editing the brightness and colour-temperature
schedule used by the sync worker.
"""

from __future__ import annotations

import math
from typing import Optional

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QBrush, QColor, QFont, QPainter, QPainterPath, QPen
from PyQt6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QPushButton,
    QSizePolicy,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from light_curve import _CURVE as _DEFAULT_CURVE

# ── Kelvin → approximate RGB (Tanner Helland algorithm) ──────────────────────

def _kelvin_to_qcolor(k: int) -> QColor:
    k = max(1000, min(10000, k))
    t = k / 100.0
    if t <= 66:
        r = 255
        g = max(0, min(255, round(99.4708025861 * math.log(t) - 161.1195681661)))
        b = 0 if t <= 19 else max(0, min(255, round(138.5177312231 * math.log(t - 10) - 305.0447927307)))
    else:
        r = max(0, min(255, round(329.698727446 * ((t - 60) ** -0.1332047592))))
        g = max(0, min(255, round(288.1221695283 * ((t - 60) ** -0.0755148492))))
        b = 255
    return QColor(r, g, b)


# ── Curve interpolation ───────────────────────────────────────────────────────

def _interp_at(waypoints: list, t: float, col: int) -> float:
    """Cosine-interpolate brightness (col=1) or kelvin (col=2) at time t."""
    t = t % 1440
    for i in range(len(waypoints) - 1):
        t0, t1 = waypoints[i][0], waypoints[i + 1][0]
        if t0 <= t < t1:
            frac = (t - t0) / (t1 - t0)
            p = (1.0 - math.cos(frac * math.pi)) / 2.0
            return waypoints[i][col] + p * (waypoints[i + 1][col] - waypoints[i][col])
    return waypoints[0][col]


# ── Canvas ────────────────────────────────────────────────────────────────────

_HANDLE_R = 6    # handle radius (px)
_HIT_R    = 10   # click detection radius (px)
_ML, _MT, _MR, _MB = 38, 12, 12, 52  # left, top, right, bottom margins


class CurvePreviewWidget(QWidget):
    """Draggable day/night curve canvas."""

    waypoints_changed = pyqtSignal(list)  # list of [min, br, k]

    def __init__(self, waypoints: list, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._wps: list[list[int]] = [list(wp) for wp in waypoints]
        self._drag_idx: Optional[int] = None
        self._drag_t_min = 0
        self._drag_t_max = 1440
        self.setMinimumSize(480, 210)
        self.setFixedHeight(210)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.setMouseTracking(True)

    # ── Public ────────────────────────────────────────────────────────────

    def set_waypoints(self, waypoints: list) -> None:
        self._wps = [list(wp) for wp in waypoints]
        self.update()

    def get_waypoints(self) -> list[tuple[int, int, int]]:
        return [tuple(wp) for wp in self._wps]  # type: ignore[return-value]

    # ── Coordinate helpers ─────────────────────────────────────────────────

    def _plot_rect(self) -> tuple[int, int, int, int]:
        w = self.width() - _ML - _MR
        h = self.height() - _MT - _MB
        return _ML, _MT, w, h

    def _to_px(self, minutes: int, brightness: int) -> tuple[int, int]:
        x0, y0, w, h = self._plot_rect()
        return int(x0 + minutes / 1440 * w), int(y0 + h - brightness / 255 * h)

    def _from_px(self, px: int, py: int) -> tuple[int, int]:
        x0, y0, w, h = self._plot_rect()
        minutes   = round((px - x0) / w * 1440)
        brightness = round((y0 + h - py) / h * 255)
        return max(0, min(1440, minutes)), max(0, min(255, brightness))

    # ── Painting ──────────────────────────────────────────────────────────

    def paintEvent(self, _event) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        x0, y0, w, h = self._plot_rect()

        # Background
        p.fillRect(self.rect(), QColor("#1e1e2e"))

        # Vertical grid (every 2 h)
        p.setPen(QPen(QColor("#2a2a45"), 1))
        for hr in range(0, 25, 2):
            px = int(x0 + hr / 24 * w)
            p.drawLine(px, y0, px, y0 + h)

        # Horizontal grid (0 %, 25 %, 50 %, 75 %, 100 %)
        for frac in (0.0, 0.25, 0.5, 0.75, 1.0):
            py = int(y0 + h * (1 - frac))
            p.drawLine(x0, py, x0 + w, py)

        # Plot border
        p.setPen(QPen(QColor("#3a3a5a"), 1))
        p.drawRect(x0, y0, w, h)

        # Colour-temp band below x-axis labels
        band_y = y0 + h + 22
        band_h = 12
        for i in range(w):
            t = i / w * 1440
            k = int(_interp_at(self._wps, t, 2))
            c = _kelvin_to_qcolor(k)
            c.setAlpha(210)
            p.fillRect(x0 + i, band_y, 1, band_h, c)
        p.setPen(QPen(QColor("#3a3a5a"), 1))
        p.drawRect(x0, band_y, w, band_h)

        # Brightness filled area
        path = QPainterPath()
        path.moveTo(x0, y0 + h)
        for i in range(w + 1):
            t = i / w * 1440
            b = _interp_at(self._wps, t, 1)
            path.lineTo(x0 + i, y0 + h - b / 255 * h)
        path.lineTo(x0 + w, y0 + h)
        path.closeSubpath()
        p.fillPath(path, QBrush(QColor(160, 180, 255, 30)))

        # Brightness curve line
        pen = QPen(QColor("#8899ee"))
        pen.setWidth(2)
        p.setPen(pen)
        prev_pt = None
        for i in range(w + 1):
            t = i / w * 1440
            b = _interp_at(self._wps, t, 1)
            pt = (x0 + i, int(y0 + h - b / 255 * h))
            if prev_pt:
                p.drawLine(prev_pt[0], prev_pt[1], pt[0], pt[1])
            prev_pt = pt

        # X-axis labels (every 4 h)
        small = QFont()
        small.setPointSize(7)
        p.setFont(small)
        p.setPen(QColor("#667788"))
        for hr in range(0, 25, 4):
            px = int(x0 + hr / 24 * w)
            p.drawText(px - 14, y0 + h + 4, 28, 14,
                       Qt.AlignmentFlag.AlignCenter, f"{hr:02d}:00")

        # Y-axis labels
        p.setPen(QColor("#667788"))
        for val, label in ((255, "255"), (128, "128"), (0, "0")):
            py = int(y0 + h - val / 255 * h)
            p.drawText(2, py - 7, _ML - 5, 14, Qt.AlignmentFlag.AlignRight, label)

        # "K" label for band
        p.drawText(2, band_y, _ML - 5, band_h,
                   Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter, "K")

        # Waypoint handles
        for i, wp in enumerate(self._wps):
            cx, cy = self._to_px(wp[0], wp[1])
            c = _kelvin_to_qcolor(wp[2])
            if i == self._drag_idx:
                p.setPen(QPen(Qt.GlobalColor.white, 2))
                p.setBrush(QBrush(c))
                p.drawEllipse(cx - _HANDLE_R - 2, cy - _HANDLE_R - 2,
                              (_HANDLE_R + 2) * 2, (_HANDLE_R + 2) * 2)
            else:
                p.setPen(QPen(QColor("#9999bb"), 1))
                p.setBrush(QBrush(c))
                p.drawEllipse(cx - _HANDLE_R, cy - _HANDLE_R,
                              _HANDLE_R * 2, _HANDLE_R * 2)

        p.end()

    # ── Mouse events ──────────────────────────────────────────────────────

    def _hit_test(self, px: float, py: float) -> Optional[int]:
        for i, wp in enumerate(self._wps):
            cx, cy = self._to_px(wp[0], wp[1])
            if abs(px - cx) <= _HIT_R and abs(py - cy) <= _HIT_R:
                return i
        return None

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            idx = self._hit_test(event.position().x(), event.position().y())
            if idx is not None:
                self._drag_idx = idx
                self._drag_t_min = self._wps[idx - 1][0] if idx > 0 else 0
                self._drag_t_max = self._wps[idx + 1][0] if idx < len(self._wps) - 1 else 1440
                self.setCursor(Qt.CursorShape.ClosedHandCursor)

    def mouseMoveEvent(self, event) -> None:
        if self._drag_idx is not None:
            minutes, brightness = self._from_px(
                int(event.position().x()), int(event.position().y())
            )
            wp = self._wps[self._drag_idx]
            wp[1] = brightness
            # First and last handles: time is locked
            if self._drag_idx not in (0, len(self._wps) - 1):
                wp[0] = max(self._drag_t_min + 1, min(self._drag_t_max - 1, minutes))
            self.update()
            self.waypoints_changed.emit([list(w) for w in self._wps])
        else:
            idx = self._hit_test(event.position().x(), event.position().y())
            self.setCursor(
                Qt.CursorShape.OpenHandCursor if idx is not None
                else Qt.CursorShape.ArrowCursor
            )

    def mouseReleaseEvent(self, event) -> None:
        if self._drag_idx is not None:
            self._drag_idx = None
            self.setCursor(Qt.CursorShape.ArrowCursor)


# ── Dialog ────────────────────────────────────────────────────────────────────

_TIME_COL = 0
_BR_COL   = 1
_K_COL    = 2


class CurveEditorDialog(QDialog):
    """Full curve editor: draggable canvas + waypoint table."""

    def __init__(self, waypoints: list, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Light Curve Editor")
        self.setMinimumWidth(560)
        self._wps: list[list[int]] = [list(wp) for wp in waypoints]
        self._updating = False

        # Canvas
        self._canvas = CurvePreviewWidget(self._wps, self)
        self._canvas.waypoints_changed.connect(self._on_canvas_changed)

        # Hint
        hint = QLabel(
            "Drag handles to adjust brightness · "
            "Left/right drag changes time (locked on first/last) · "
            "Double-click a cell to type an exact value"
        )
        hint.setStyleSheet("color: #667788; font-size: 10px;")
        hint.setAlignment(Qt.AlignmentFlag.AlignCenter)

        # Table
        self._table = QTableWidget(0, 3, self)
        self._table.setHorizontalHeaderLabels(["Time", "Brightness  (0–255)", "Color Temp  (K)"])
        self._table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self._table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self._table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        self._table.setAlternatingRowColors(True)
        self._table.setMaximumHeight(220)
        self._table.itemChanged.connect(self._on_table_changed)
        self._populate_table()

        # Bottom buttons
        add_btn    = QPushButton("＋  Add Waypoint")
        remove_btn = QPushButton("－  Remove Selected")
        reset_btn  = QPushButton("↺  Reset to Defaults")
        add_btn.clicked.connect(self._add_waypoint)
        remove_btn.clicked.connect(self._remove_waypoint)
        reset_btn.clicked.connect(self._reset_defaults)

        btn_row = QHBoxLayout()
        btn_row.addWidget(add_btn)
        btn_row.addWidget(remove_btn)
        btn_row.addStretch()
        btn_row.addWidget(reset_btn)

        box = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        box.accepted.connect(self.accept)
        box.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.addWidget(self._canvas)
        layout.addWidget(hint)
        layout.addWidget(self._table)
        layout.addLayout(btn_row)
        layout.addWidget(box)

    def get_waypoints(self) -> list[list[int]]:
        return [list(wp) for wp in self._wps]

    # ── Table helpers ─────────────────────────────────────────────────────

    def _populate_table(self) -> None:
        self._updating = True
        self._table.setRowCount(0)
        for i, wp in enumerate(self._wps):
            self._table.insertRow(i)
            self._fill_row(i, wp, locked=(i == 0 or i == len(self._wps) - 1))
        self._updating = False

    def _fill_row(self, row: int, wp: list[int], locked: bool = False) -> None:
        t = wp[0]
        time_item = QTableWidgetItem(f"{t // 60:02d}:{t % 60:02d}")
        if locked:
            time_item.setFlags(time_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            time_item.setForeground(QColor("#667788"))
        self._table.setItem(row, _TIME_COL, time_item)
        self._table.setItem(row, _BR_COL, QTableWidgetItem(str(wp[1])))
        k_item = QTableWidgetItem(str(wp[2]))
        c = _kelvin_to_qcolor(wp[2])
        c.setAlpha(55)
        k_item.setBackground(QBrush(c))
        self._table.setItem(row, _K_COL, k_item)

    # ── Canvas → table sync ───────────────────────────────────────────────

    def _on_canvas_changed(self, wps: list) -> None:
        self._wps = [list(w) for w in wps]
        self._updating = True
        for i, wp in enumerate(self._wps):
            if i >= self._table.rowCount():
                break
            locked = (i == 0 or i == len(self._wps) - 1)
            t = wp[0]
            time_item = QTableWidgetItem(f"{t // 60:02d}:{t % 60:02d}")
            if locked:
                time_item.setFlags(time_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
                time_item.setForeground(QColor("#667788"))
            self._table.setItem(i, _TIME_COL, time_item)
            self._table.setItem(i, _BR_COL, QTableWidgetItem(str(wp[1])))
            k_item = QTableWidgetItem(str(wp[2]))
            c = _kelvin_to_qcolor(wp[2])
            c.setAlpha(55)
            k_item.setBackground(QBrush(c))
            self._table.setItem(i, _K_COL, k_item)
        self._updating = False

    # ── Table → canvas sync ───────────────────────────────────────────────

    def _on_table_changed(self, item: QTableWidgetItem) -> None:
        if self._updating:
            return
        row = item.row()
        col = item.column()
        text = item.text().strip()
        try:
            if col == _TIME_COL:
                parts = text.split(":")
                if len(parts) != 2:
                    raise ValueError
                hh, mm = int(parts[0]), int(parts[1])
                if not (0 <= hh <= 23 and 0 <= mm <= 59):
                    raise ValueError
                minutes = hh * 60 + mm
                t_prev = self._wps[row - 1][0] if row > 0 else -1
                t_next = self._wps[row + 1][0] if row < len(self._wps) - 1 else 1441
                if not (t_prev < minutes < t_next):
                    raise ValueError
                self._wps[row][0] = minutes
            elif col == _BR_COL:
                v = int(text)
                if not (0 <= v <= 255):
                    raise ValueError
                self._wps[row][1] = v
            elif col == _K_COL:
                v = int(text)
                if not (1000 <= v <= 10000):
                    raise ValueError
                self._wps[row][2] = v
                # Refresh swatch without re-entering this handler
                self._updating = True
                c = _kelvin_to_qcolor(v)
                c.setAlpha(55)
                self._table.item(row, _K_COL).setBackground(QBrush(c))
                self._updating = False
        except (ValueError, IndexError):
            # Revert the cell to the current waypoint value
            self._updating = True
            locked = (row == 0 or row == len(self._wps) - 1)
            self._fill_row(row, self._wps[row], locked=locked)
            self._updating = False
            return

        self._canvas.set_waypoints(self._wps)

    # ── Add / Remove / Reset ──────────────────────────────────────────────

    def _add_waypoint(self) -> None:
        sel = self._table.selectedItems()
        row = sel[0].row() if sel else len(self._wps) - 2
        row = max(0, min(row, len(self._wps) - 2))
        t0, t1 = self._wps[row][0], self._wps[row + 1][0]
        if t1 - t0 < 2:
            return
        new_t = (t0 + t1) // 2
        new_b = round(_interp_at(self._wps, new_t, 1))
        new_k = round(_interp_at(self._wps, new_t, 2))
        self._wps.insert(row + 1, [new_t, new_b, new_k])
        self._populate_table()
        self._canvas.set_waypoints(self._wps)
        self._table.selectRow(row + 1)

    def _remove_waypoint(self) -> None:
        if len(self._wps) <= 3:
            return
        sel = self._table.selectedItems()
        if not sel:
            return
        row = sel[0].row()
        if row == 0 or row == len(self._wps) - 1:
            return
        del self._wps[row]
        self._populate_table()
        self._canvas.set_waypoints(self._wps)

    def _reset_defaults(self) -> None:
        self._wps = [list(wp) for wp in _DEFAULT_CURVE]
        self._populate_table()
        self._canvas.set_waypoints(self._wps)
