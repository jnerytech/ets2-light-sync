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
from light_curve import DEFAULT_WAYPOINTS


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

        # ── Astronomical lighting ─────────────────────────────────────────────
        self._astronomical_lighting = QCheckBox(
            "Astronomical lighting (dynamic curve from real sunrise/sunset at truck position)"
        )
        self._astronomical_lighting.setChecked(bool(self._cfg.get("astronomical_lighting", True)))

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
        layout.addWidget(self._astronomical_lighting)
        layout.addSpacing(8)
        layout.addWidget(curve_group)
        layout.addWidget(buttons)

    # ── Private ───────────────────────────────────────────────────────────────

    def _refresh_curve_label(self) -> None:
        if self._light_curve is None:
            self._curve_status.setText("Using astronomical lighting  (no override)")
            self._curve_status.setStyleSheet("color: #778899;")
        else:
            self._curve_status.setText(f"Custom curve  ({len(self._light_curve)} waypoints)")
            self._curve_status.setStyleSheet("")

    def _open_curve_editor(self) -> None:
        wps = self._light_curve if self._light_curve is not None else list(DEFAULT_WAYPOINTS)
        dlg = CurveEditorDialog(wps, self)
        if dlg.exec():
            self._light_curve = dlg.get_waypoints()
            self._refresh_curve_label()

    def _reset_to_defaults(self) -> None:
        d = config.defaults()
        self._ha_url.setText(str(d["ha_url"]))
        # token intentionally not reset
        self._entity_id.setText(str(d["entity_id"]))
        self._poll_interval.setValue(float(d["poll_interval"]))
        self._transition_time.setValue(float(d["transition_time"]))
        self._default_brightness.setValue(int(d["default_brightness"]))
        self._default_color_temp_k.setValue(int(d["default_color_temp_k"]))
        self._astronomical_lighting.setChecked(bool(d["astronomical_lighting"]))
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
            "astronomical_lighting": self._astronomical_lighting.isChecked(),
            "light_curve": self._light_curve,
        }
        config.save(data)
        self.accept()
