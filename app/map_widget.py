"""
app/map_widget.py – Europe map panel with live tracking and simulation mode.

Features
--------
- QPainter-based canvas; no WebEngine dependency.
- Background map: Natural Earth raster, downloaded once to data/map_europe.png.
- Live mode: follows the truck position from SyncWorker.position_updated signal.
- Simulation mode: click on map to set virtual position; time slider scrubs
  the full 24-hour cycle; Play/Pause animates one game day in ~30 real seconds.
- Sun info panel: shows country, timezone, UTC offset, sunrise, sunset, and a
  real-time brightness preview bar.

Map bounds (equirectangular projection)
  lat: 33° N – 72° N   lon: −12° E – 42° E
"""

import datetime
import logging
import math
from pathlib import Path
from typing import Optional

from PyQt6.QtCore import (
    QObject,
    QPoint,
    QRect,
    QSize,
    Qt,
    QThread,
    QTimer,
    pyqtSignal,
)
from PyQt6.QtGui import (
    QBrush,
    QColor,
    QFont,
    QPainter,
    QPen,
    QPixmap,
)
from PyQt6.QtWidgets import (
    QButtonGroup,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QProgressBar,
    QPushButton,
    QRadioButton,
    QSizePolicy,
    QSlider,
    QVBoxLayout,
    QWidget,
)

from light_curve import DEFAULT_WAYPOINTS as _BUILTIN_CURVE, calculate_light
from location import ets2_to_latlon, get_country_name
from sun_times import get_sun_curve

log = logging.getLogger(__name__)

# ── Map geographic bounds ──────────────────────────────────────────────────────
_LAT_MIN =  33.0
_LAT_MAX =  72.0
_LON_MIN = -12.0
_LON_MAX =  42.0

# ETS2 world-space bounds for the inverse conversion (approx)
# These are derived from the calibration constants in location.py
_REF_X   = -31600.0
_REF_Z   = -62000.0
_REF_LAT =  48.8566
_REF_LON =   2.3522
_SCALE_LON = (13.4050 - 2.3522) / (17400.0 - (-31600.0))
_SCALE_LAT = (52.5200 - 48.8566) / (-39200.0 - (-62000.0))

_MAP_PNG = Path(__file__).parent.parent / "data" / "map_europe.png"
_MAP_URL = "https://naciscdn.org/naturalearth/50m/raster/NE2_50M_SR_W.zip"

# Animation: one full game-day (1440 min) in 30 real seconds
_ANIM_GAME_MINUTES_PER_REAL_SECOND = 1440.0 / 30.0


def _latlon_to_canvas(lat: float, lon: float, w: int, h: int) -> tuple[int, int]:
    """Map geographic coordinates to canvas pixel position."""
    px = int((lon - _LON_MIN) / (_LON_MAX - _LON_MIN) * w)
    py = int((1.0 - (lat - _LAT_MIN) / (_LAT_MAX - _LAT_MIN)) * h)
    return px, py


def _canvas_to_latlon(px: int, py: int, w: int, h: int) -> tuple[float, float]:
    """Map canvas pixel position to geographic coordinates."""
    lon = _LON_MIN + (px / w) * (_LON_MAX - _LON_MIN)
    lat = _LAT_MIN + (1.0 - py / h) * (_LAT_MAX - _LAT_MIN)
    return lat, lon


def _latlon_to_ets2(lat: float, lon: float) -> tuple[float, float]:
    """Inverse of ets2_to_latlon: real-world lat/lon → ETS2 world coordinates."""
    z = _REF_Z + (lat - _REF_LAT) / _SCALE_LAT
    x = _REF_X + (lon - _REF_LON) / _SCALE_LON
    return x, z


# ── Map downloader ─────────────────────────────────────────────────────────────

class _MapDownloader(QThread):
    """Downloads and crops the Natural Earth raster to data/map_europe.png."""

    progress = pyqtSignal(int)   # 0–100
    finished = pyqtSignal(bool)  # True = success

    def run(self) -> None:
        try:
            import io
            import zipfile

            import requests
            from PIL import Image

            log.info("Downloading Natural Earth map…")
            self.progress.emit(5)

            resp = requests.get(_MAP_URL, stream=True, timeout=60)
            resp.raise_for_status()
            total = int(resp.headers.get("content-length", 0))
            data = b""
            downloaded = 0
            for chunk in resp.iter_content(chunk_size=65536):
                data += chunk
                downloaded += len(chunk)
                if total > 0:
                    self.progress.emit(5 + int(downloaded / total * 60))

            self.progress.emit(70)
            log.info("Extracting and cropping map…")

            with zipfile.ZipFile(io.BytesIO(data)) as zf:
                # Find the main raster file inside the ZIP
                tif_names = [n for n in zf.namelist() if n.endswith(".tif") or n.endswith(".tiff") or n.endswith(".png")]
                if not tif_names:
                    raise RuntimeError("No raster image found in ZIP")
                img_data = zf.read(tif_names[0])

            self.progress.emit(80)
            img = Image.open(io.BytesIO(img_data))

            # Natural Earth 50m covers full world — crop to ETS2 Europe bounds
            # Image spans lat -90..90, lon -180..180
            w_full, h_full = img.size
            left   = int(((_LON_MIN + 180) / 360.0) * w_full)
            right  = int(((_LON_MAX + 180) / 360.0) * w_full)
            top    = int(((90 - _LAT_MAX) / 180.0) * h_full)
            bottom = int(((90 - _LAT_MIN) / 180.0) * h_full)
            cropped = img.crop((left, top, right, bottom))
            # Resize to a manageable size
            target_w = 900
            target_h = int(target_w * (bottom - top) / (right - left))
            resized = cropped.resize((target_w, target_h), Image.LANCZOS)

            self.progress.emit(95)
            _MAP_PNG.parent.mkdir(parents=True, exist_ok=True)
            resized.save(str(_MAP_PNG), "PNG")
            log.info("Map saved to %s", _MAP_PNG)
            self.progress.emit(100)
            self.finished.emit(True)

        except Exception as exc:
            log.warning("Map download failed: %s", exc)
            self.finished.emit(False)


# ── Map canvas ─────────────────────────────────────────────────────────────────

class MapCanvas(QWidget):
    """QPainter canvas that shows the Europe map with a truck position dot."""

    sim_position_changed = pyqtSignal(float, float)  # truck_x, truck_z

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._pixmap: Optional[QPixmap] = None
        self._truck_x: Optional[float] = None
        self._truck_z: Optional[float] = None
        self._sim_mode = False
        self.setMinimumSize(400, 280)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.setCursor(Qt.CursorShape.CrossCursor)
        self._load_pixmap()

    def _load_pixmap(self) -> None:
        if _MAP_PNG.exists():
            px = QPixmap(str(_MAP_PNG))
            self._pixmap = px if not px.isNull() else None

    def reload_pixmap(self) -> None:
        self._load_pixmap()
        self.update()

    def set_sim_mode(self, enabled: bool) -> None:
        self._sim_mode = enabled
        self.setCursor(Qt.CursorShape.CrossCursor if enabled else Qt.CursorShape.ArrowCursor)

    def update_truck_position(self, truck_x: float, truck_z: float) -> None:
        self._truck_x = truck_x
        self._truck_z = truck_z
        self.update()

    def mousePressEvent(self, event) -> None:
        if not self._sim_mode:
            return
        if event.button() != Qt.MouseButton.LeftButton:
            return
        w, h = self.width(), self.height()
        lat, lon = _canvas_to_latlon(event.pos().x(), event.pos().y(), w, h)
        # Clamp to ETS2 map bounds
        lat = max(_LAT_MIN, min(_LAT_MAX, lat))
        lon = max(_LON_MIN, min(_LON_MAX, lon))
        x, z = _latlon_to_ets2(lat, lon)
        self._truck_x = x
        self._truck_z = z
        self.sim_position_changed.emit(x, z)
        self.update()

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        w, h = self.width(), self.height()

        # Background
        if self._pixmap:
            painter.drawPixmap(QRect(0, 0, w, h), self._pixmap)
        else:
            painter.fillRect(0, 0, w, h, QColor(30, 60, 90))
            painter.setPen(QColor(180, 200, 220))
            painter.setFont(QFont("Consolas", 10))
            painter.drawText(
                QRect(0, 0, w, h),
                Qt.AlignmentFlag.AlignCenter,
                "Map not downloaded.\nClick 'Download Map' below.",
            )

        # Truck dot
        if self._truck_x is not None and self._truck_z is not None:
            lat, lon = ets2_to_latlon(self._truck_x, self._truck_z)
            if _LAT_MIN <= lat <= _LAT_MAX and _LON_MIN <= lon <= _LON_MAX:
                px, py = _latlon_to_canvas(lat, lon, w, h)
                # Outer ring
                painter.setPen(QPen(QColor(255, 255, 255), 2))
                painter.setBrush(QBrush(QColor(220, 50, 50)))
                painter.drawEllipse(QPoint(px, py), 7, 7)
                # Inner dot
                painter.setBrush(QBrush(QColor(255, 255, 255)))
                painter.setPen(Qt.PenStyle.NoPen)
                painter.drawEllipse(QPoint(px, py), 3, 3)

        painter.end()


# ── Sun info panel ─────────────────────────────────────────────────────────────

class _SunInfoPanel(QWidget):
    """Shows country, timezone, sunrise/sunset, game day, and a brightness preview."""

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._lbl_country  = QLabel("Country: —")
        self._lbl_tz       = QLabel("Timezone: —")
        self._lbl_sunrise  = QLabel("Sunrise: —")
        self._lbl_sunset   = QLabel("Sunset: —")
        self._lbl_game_day = QLabel("Game day: —")
        self._lbl_bright   = QLabel("Brightness: —")
        self._bar          = QProgressBar()
        self._bar.setRange(0, 255)
        self._bar.setValue(0)
        self._bar.setTextVisible(False)
        self._bar.setMaximumHeight(12)

        col1 = QVBoxLayout()
        col1.addWidget(self._lbl_country)
        col1.addWidget(self._lbl_tz)

        col2 = QVBoxLayout()
        col2.addWidget(self._lbl_sunrise)
        col2.addWidget(self._lbl_sunset)

        col3 = QVBoxLayout()
        col3.addWidget(self._lbl_game_day)

        cols = QHBoxLayout()
        cols.addLayout(col1)
        cols.addSpacing(16)
        cols.addLayout(col2)
        cols.addSpacing(16)
        cols.addLayout(col3)
        cols.addStretch()

        bright_row = QHBoxLayout()
        bright_row.addWidget(self._lbl_bright)
        bright_row.addWidget(self._bar, 1)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.addLayout(cols)
        layout.addLayout(bright_row)

    def update_info(
        self,
        country: Optional[str],
        tz_name: Optional[str],
        utc_offset: int,
        sunrise_min: Optional[int],
        sunset_min: Optional[int],
        brightness: int,
        game_day: Optional[int] = None,
    ) -> None:
        self._lbl_country.setText(f"Country: {country or '—'}")
        if tz_name:
            h, m = divmod(abs(utc_offset), 60)
            sign = "+" if utc_offset >= 0 else "-"
            tz_str = f"UTC{sign}{h}" if m == 0 else f"UTC{sign}{h}:{m:02d}"
            self._lbl_tz.setText(f"Timezone: {tz_name}  ({tz_str})")
        else:
            self._lbl_tz.setText("Timezone: —")

        def fmt(m: Optional[int]) -> str:
            return f"{m // 60:02d}:{m % 60:02d}" if m is not None else "—"

        self._lbl_sunrise.setText(f"Sunrise: {fmt(sunrise_min)}")
        self._lbl_sunset.setText(f"Sunset: {fmt(sunset_min)}")
        self._lbl_game_day.setText(f"Game day: {game_day}" if game_day is not None else "Game day: —")
        self._lbl_bright.setText(f"Brightness: {brightness}/255")
        self._bar.setValue(brightness)


# ── Main map panel ─────────────────────────────────────────────────────────────

class MapPanel(QWidget):
    """Full map tab: canvas + mode toggle + time slider + sun info."""

    sim_light_update = pyqtSignal(int, int)  # brightness, kelvin — emitted in simulation mode

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)

        # ── State ─────────────────────────────────────────────────────────────
        self._sim_truck_x: float = -31600.0   # Paris as default
        self._sim_truck_z: float = -62000.0
        self._live_truck_x: Optional[float] = None
        self._live_truck_z: Optional[float] = None
        self._current_tz_name: Optional[str] = None
        self._current_country: Optional[str] = None
        self._current_utc_offset: int = 0
        self._current_sun_curve: Optional[list] = None
        self._live_game_day: Optional[int] = None
        self._anim_timer = QTimer(self)
        self._anim_timer.setInterval(50)  # 20 fps
        self._anim_timer.timeout.connect(self._anim_tick)
        self._anim_running = False

        # ── Map canvas ────────────────────────────────────────────────────────
        self._canvas = MapCanvas(self)
        self._canvas.sim_position_changed.connect(self._on_sim_position_changed)

        # ── Mode selector ─────────────────────────────────────────────────────
        self._radio_live = QRadioButton("Live (ETS2)")
        self._radio_sim  = QRadioButton("Simulation")
        self._radio_live.setChecked(True)
        mode_group = QButtonGroup(self)
        mode_group.addButton(self._radio_live)
        mode_group.addButton(self._radio_sim)
        self._radio_live.toggled.connect(self._on_mode_changed)  # type: ignore[misc]

        mode_row = QHBoxLayout()
        mode_row.addWidget(self._radio_live)
        mode_row.addWidget(self._radio_sim)
        mode_row.addStretch()

        # ── Download button (shown when map is missing) ───────────────────────
        self._dl_btn = QPushButton("Download Map")
        self._dl_btn.clicked.connect(self._start_download)  # type: ignore[misc]
        self._dl_progress = QProgressBar()
        self._dl_progress.setRange(0, 100)
        self._dl_progress.setVisible(False)
        self._dl_btn.setVisible(not _MAP_PNG.exists())

        dl_row = QHBoxLayout()
        dl_row.addStretch()
        dl_row.addWidget(self._dl_btn)
        dl_row.addWidget(self._dl_progress)

        # ── Time slider ───────────────────────────────────────────────────────
        self._slider = QSlider(Qt.Orientation.Horizontal)
        self._slider.setRange(0, 1439)
        self._slider.setValue(720)  # noon
        self._slider.setTickInterval(60)
        self._slider.setEnabled(False)
        self._slider.valueChanged.connect(self._on_slider_changed)  # type: ignore[misc]

        self._time_label = QLabel("12:00")
        self._time_label.setFixedWidth(38)

        self._play_btn = QPushButton("▶")
        self._play_btn.setFixedWidth(32)
        self._play_btn.setEnabled(False)
        self._play_btn.clicked.connect(self._toggle_anim)  # type: ignore[misc]

        slider_row = QHBoxLayout()
        slider_row.addWidget(QLabel("Time:"))
        slider_row.addWidget(self._slider, 1)
        slider_row.addWidget(self._time_label)
        slider_row.addWidget(self._play_btn)

        # ── Sun info panel ────────────────────────────────────────────────────
        self._info_panel = _SunInfoPanel(self)
        info_box = QGroupBox()
        box_layout = QVBoxLayout(info_box)
        box_layout.setContentsMargins(4, 4, 4, 4)
        box_layout.addWidget(self._info_panel)

        # ── Layout ────────────────────────────────────────────────────────────
        layout = QVBoxLayout(self)
        layout.addLayout(mode_row)
        layout.addWidget(self._canvas, 1)
        layout.addLayout(dl_row)
        layout.addLayout(slider_row)
        layout.addWidget(info_box)

        self._refresh_info()

    # ── Public API ─────────────────────────────────────────────────────────────

    def on_position_updated(self, truck_x: float, truck_z: float) -> None:
        """Called by SyncWorker.position_updated signal (live mode only)."""
        self._live_truck_x = truck_x
        self._live_truck_z = truck_z
        if self._radio_live.isChecked():
            self._canvas.update_truck_position(truck_x, truck_z)

    def on_light_updated(
        self,
        game_day: int,
        game_time: int,
        brightness: int,
        kelvin: int,
        tz_name: str,
        country_name: str,
    ) -> None:
        """Called by SyncWorker.light_updated signal (live mode only)."""
        if self._radio_live.isChecked():
            self._current_tz_name    = tz_name or None
            self._current_country    = country_name or None
            self._current_utc_offset = 0  # offset is baked into curve
            self._live_game_day      = game_day
            # Refresh sun info with live data
            self._refresh_info_live(game_time, brightness)

    # ── Private ────────────────────────────────────────────────────────────────

    def _on_mode_changed(self, live: bool) -> None:
        is_sim = not live
        self._canvas.set_sim_mode(is_sim)
        self._slider.setEnabled(is_sim)
        self._play_btn.setEnabled(is_sim)
        if is_sim:
            self._canvas.update_truck_position(self._sim_truck_x, self._sim_truck_z)
            self._refresh_info()
        else:
            if self._anim_running:
                self._toggle_anim()
            if self._live_truck_x is not None:
                self._canvas.update_truck_position(self._live_truck_x, self._live_truck_z)

    def _on_sim_position_changed(self, truck_x: float, truck_z: float) -> None:
        self._sim_truck_x = truck_x
        self._sim_truck_z = truck_z
        self._current_sun_curve = None  # force recompute
        self._refresh_info()

    def _on_slider_changed(self, value: int) -> None:
        h, m = divmod(value, 60)
        self._time_label.setText(f"{h:02d}:{m:02d}")
        self._refresh_info()

    def _toggle_anim(self) -> None:
        if self._anim_running:
            self._anim_timer.stop()
            self._anim_running = False
            self._play_btn.setText("▶")
        else:
            self._anim_timer.start()
            self._anim_running = True
            self._play_btn.setText("■")

    def _anim_tick(self) -> None:
        step = int(_ANIM_GAME_MINUTES_PER_REAL_SECOND * 0.05)  # 50 ms interval
        val = (self._slider.value() + max(1, step)) % 1440
        self._slider.setValue(val)

    def _get_sim_location(self):
        """Return LocationInfo for the current simulated position."""
        from location import get_location
        return get_location(self._sim_truck_x, self._sim_truck_z)

    def _refresh_info(self) -> None:
        """Update sun info panel in simulation mode."""
        if not self._radio_sim.isChecked():
            return
        game_time = self._slider.value()
        loc = self._get_sim_location()
        if loc is None or loc.tz_name is None:
            self._info_panel.update_info(None, None, 0, None, None, 0)
            return

        self._current_tz_name    = loc.tz_name
        self._current_country    = loc.country_name
        self._current_utc_offset = loc.utc_offset_minutes

        if self._current_sun_curve is None:
            self._current_sun_curve = get_sun_curve(loc.lat, loc.lon, loc.tz_name)

        curve = self._current_sun_curve or list(_BUILTIN_CURVE)
        brightness, color_temp = calculate_light(game_time, curve)

        # Extract sunrise/sunset from curve
        sunrise_min, sunset_min = _extract_sunrise_sunset(curve)

        self._info_panel.update_info(
            loc.country_name,
            loc.tz_name,
            loc.utc_offset_minutes,
            sunrise_min,
            sunset_min,
            brightness,
        )

        self.sim_light_update.emit(brightness, color_temp)

    def _refresh_info_live(self, game_time: int, brightness: int) -> None:
        """Update sun info panel in live mode (data from SyncWorker)."""
        # Re-derive sun curve for display purposes
        if self._live_truck_x is not None and self._current_tz_name:
            from location import ets2_to_latlon
            lat, lon = ets2_to_latlon(self._live_truck_x, self._live_truck_z)
            curve = get_sun_curve(lat, lon, self._current_tz_name) or list(_BUILTIN_CURVE)
            sunrise_min, sunset_min = _extract_sunrise_sunset(curve)
        else:
            sunrise_min = sunset_min = None

        self._info_panel.update_info(
            self._current_country,
            self._current_tz_name,
            self._current_utc_offset,
            sunrise_min,
            sunset_min,
            brightness,
            game_day=self._live_game_day,
        )

    def _start_download(self) -> None:
        self._dl_btn.setEnabled(False)
        self._dl_progress.setVisible(True)
        self._dl_progress.setValue(0)
        self._downloader = _MapDownloader(self)
        self._downloader.progress.connect(self._dl_progress.setValue)  # type: ignore[misc]
        self._downloader.finished.connect(self._on_download_finished)  # type: ignore[misc]
        self._downloader.start()

    def _on_download_finished(self, success: bool) -> None:
        self._dl_progress.setVisible(False)
        if success:
            self._canvas.reload_pixmap()
            self._dl_btn.setVisible(False)
        else:
            self._dl_btn.setEnabled(True)
            self._dl_btn.setText("Retry Download")


def _extract_sunrise_sunset(
    curve: list,
) -> tuple[Optional[int], Optional[int]]:
    """Find approximate sunrise and sunset times from a curve.

    Sunrise = first transition to brightness >= 200.
    Sunset  = last time brightness >= 200 before going dark.
    """
    sunrise_min: Optional[int] = None
    sunset_min:  Optional[int] = None
    for i in range(len(curve) - 1):
        t0, b0, _ = curve[i]
        t1, b1, _ = curve[i + 1]
        if b0 < 200 <= b1 and sunrise_min is None:
            sunrise_min = t0
        if b0 >= 200 > b1:
            sunset_min = t0
    return sunrise_min, sunset_min
