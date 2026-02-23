"""
app/settings_dialog.py – Settings dialog for ETS2 Light Sync.

Displays all fields from config/settings.json.  OK saves; Cancel discards.
"""

from PyQt6.QtWidgets import (
    QCheckBox,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
)

from app import config
from app.curve_editor import CurveEditorDialog
from light_curve import _CURVE as _DEFAULT_CURVE


class SettingsDialog(QDialog):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Settings")
        self.setMinimumWidth(400)

        self._cfg = config.load()
        # Custom curve: None = use built-in default; list-of-lists = user-edited
        self._light_curve: list | None = self._cfg.get("light_curve")

        # ── Home Assistant fields ─────────────────────────────────────────────
        self._ha_url = QLineEdit(self._cfg.get("ha_url", ""))
        self._ha_token = QLineEdit(self._cfg.get("ha_token", ""))
        self._ha_token.setEchoMode(QLineEdit.EchoMode.Password)
        self._entity_id = QLineEdit(self._cfg.get("entity_id", ""))

        self._poll_interval = QDoubleSpinBox()
        self._poll_interval.setRange(1.0, 300.0)
        self._poll_interval.setSingleStep(1.0)
        self._poll_interval.setSuffix(" s")
        self._poll_interval.setValue(float(self._cfg.get("poll_interval", 15)))

        self._transition_time = QDoubleSpinBox()
        self._transition_time.setRange(0.0, 10.0)
        self._transition_time.setSingleStep(0.5)
        self._transition_time.setSuffix(" s")
        self._transition_time.setValue(float(self._cfg.get("transition_time", 1)))

        self._default_brightness = QSpinBox()
        self._default_brightness.setRange(0, 255)
        self._default_brightness.setValue(int(self._cfg.get("default_brightness", 255)))

        self._default_color_temp_k = QSpinBox()
        self._default_color_temp_k.setRange(1000, 10000)
        self._default_color_temp_k.setSingleStep(100)
        self._default_color_temp_k.setSuffix(" K")
        self._default_color_temp_k.setValue(int(self._cfg.get("default_color_temp_k", 4000)))

        ha_form = QFormLayout()
        ha_form.addRow("HA URL:", self._ha_url)
        ha_form.addRow("HA Token:", self._ha_token)
        ha_form.addRow("Entity ID:", self._entity_id)
        ha_form.addRow("Poll Interval:", self._poll_interval)
        ha_form.addRow("Transition Time:", self._transition_time)
        ha_form.addRow("Default Brightness:", self._default_brightness)
        ha_form.addRow("Default Color Temp:", self._default_color_temp_k)

        # ── Simulation mode fields ────────────────────────────────────────────
        self._sim_mode = QCheckBox("Enable simulation mode (no ETS2 required)")
        self._sim_mode.setChecked(bool(self._cfg.get("sim_mode", False)))

        self._sim_time_start = QSpinBox()
        self._sim_time_start.setRange(0, 1439)
        self._sim_time_start.setSuffix(" min")
        self._sim_time_start.setToolTip("Start time in minutes since midnight (360 = 06:00)")
        self._sim_time_start.setValue(int(self._cfg.get("sim_time_start", 360)))

        self._sim_time_speed = QDoubleSpinBox()
        self._sim_time_speed.setRange(1.0, 3600.0)
        self._sim_time_speed.setSingleStep(10.0)
        self._sim_time_speed.setSuffix("× ")
        self._sim_time_speed.setToolTip("Game-minutes elapsed per real-second")
        self._sim_time_speed.setValue(float(self._cfg.get("sim_time_speed", 60.0)))

        sim_form = QFormLayout()
        sim_form.addRow("Start Time:", self._sim_time_start)
        sim_form.addRow("Speed:", self._sim_time_speed)

        self._sim_group = QGroupBox()
        self._sim_group.setLayout(sim_form)
        self._sim_group.setEnabled(self._sim_mode.isChecked())
        self._sim_mode.toggled.connect(self._sim_group.setEnabled)  # type: ignore[misc]

        sim_layout = QVBoxLayout()
        sim_layout.addWidget(self._sim_mode)
        sim_layout.addWidget(self._sim_group)

        # ── Light curve ───────────────────────────────────────────────────────
        self._curve_status = QLabel()
        self._refresh_curve_label()
        edit_curve_btn = QPushButton("Edit Light Curve…")
        edit_curve_btn.clicked.connect(self._open_curve_editor)  # type: ignore[misc]
        curve_row = QHBoxLayout()
        curve_row.addWidget(self._curve_status)
        curve_row.addStretch()
        curve_row.addWidget(edit_curve_btn)
        curve_group = QGroupBox("Light Curve")
        curve_group.setLayout(curve_row)

        # ── Dialog layout ─────────────────────────────────────────────────────
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self._save_and_accept)  # type: ignore[misc]
        buttons.rejected.connect(self.reject)  # type: ignore[misc]

        reset_btn = QPushButton("Reset to Defaults")
        reset_btn.clicked.connect(self._reset_to_defaults)  # type: ignore[misc]
        buttons.addButton(reset_btn, QDialogButtonBox.ButtonRole.ResetRole)

        layout = QVBoxLayout(self)
        layout.addLayout(ha_form)
        layout.addSpacing(8)
        layout.addLayout(sim_layout)
        layout.addSpacing(8)
        layout.addWidget(curve_group)
        layout.addWidget(buttons)

    # ── Private ───────────────────────────────────────────────────────────────

    def _refresh_curve_label(self) -> None:
        if self._light_curve is None:
            self._curve_status.setText(f"Using built-in default  ({len(_DEFAULT_CURVE)} waypoints)")
            self._curve_status.setStyleSheet("color: #778899;")
        else:
            self._curve_status.setText(f"Custom curve  ({len(self._light_curve)} waypoints)")
            self._curve_status.setStyleSheet("")

    def _open_curve_editor(self) -> None:
        wps = self._light_curve if self._light_curve is not None else list(_DEFAULT_CURVE)
        dlg = CurveEditorDialog(wps, self)
        if dlg.exec():
            self._light_curve = dlg.get_waypoints()
            self._refresh_curve_label()

    def _reset_to_defaults(self) -> None:
        d = config._DEFAULTS
        self._ha_url.setText(str(d["ha_url"]))
        # token intentionally not reset
        self._entity_id.setText(str(d["entity_id"]))
        self._poll_interval.setValue(float(d["poll_interval"]))
        self._transition_time.setValue(float(d["transition_time"]))
        self._default_brightness.setValue(int(d["default_brightness"]))
        self._default_color_temp_k.setValue(int(d["default_color_temp_k"]))
        self._sim_mode.setChecked(bool(d["sim_mode"]))
        self._sim_time_start.setValue(int(d["sim_time_start"]))
        self._sim_time_speed.setValue(float(d["sim_time_speed"]))
        self._light_curve = None
        self._refresh_curve_label()

    def _save_and_accept(self) -> None:
        data = {
            "ha_url": self._ha_url.text().strip(),
            "ha_token": self._ha_token.text().strip(),
            "entity_id": self._entity_id.text().strip(),
            "poll_interval": self._poll_interval.value(),
            "transition_time": self._transition_time.value(),
            "default_brightness": self._default_brightness.value(),
            "default_color_temp_k": self._default_color_temp_k.value(),
            "sim_mode": self._sim_mode.isChecked(),
            "sim_time_start": self._sim_time_start.value(),
            "sim_time_speed": self._sim_time_speed.value(),
            "light_curve": self._light_curve,
        }
        config.save(data)
        self.accept()
