"""
app/settings_dialog.py – Settings dialog for ETS2 Light Sync.

Displays all fields from config/settings.json.  OK saves; Cancel discards.
"""

from PyQt6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFormLayout,
    QLineEdit,
    QSpinBox,
    QVBoxLayout,
)

from app import config


class SettingsDialog(QDialog):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Settings")
        self.setMinimumWidth(400)

        self._cfg = config.load()

        # ── Fields ───────────────────────────────────────────────────────────
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

        # ── Layout ────────────────────────────────────────────────────────────
        form = QFormLayout()
        form.addRow("HA URL:", self._ha_url)
        form.addRow("HA Token:", self._ha_token)
        form.addRow("Entity ID:", self._entity_id)
        form.addRow("Poll Interval:", self._poll_interval)
        form.addRow("Transition Time:", self._transition_time)
        form.addRow("Default Brightness:", self._default_brightness)
        form.addRow("Default Color Temp:", self._default_color_temp_k)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self._save_and_accept)
        buttons.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.addLayout(form)
        layout.addWidget(buttons)

    # ── Private ───────────────────────────────────────────────────────────────

    def _save_and_accept(self) -> None:
        data = {
            "ha_url": self._ha_url.text().strip(),
            "ha_token": self._ha_token.text().strip(),
            "entity_id": self._entity_id.text().strip(),
            "poll_interval": self._poll_interval.value(),
            "transition_time": self._transition_time.value(),
            "default_brightness": self._default_brightness.value(),
            "default_color_temp_k": self._default_color_temp_k.value(),
        }
        config.save(data)
        self.accept()
