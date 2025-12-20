from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QComboBox,
    QCheckBox,
)


class DisplayChoiceDialog(QDialog):
    """Small first-launch dialog to pick a display and demo mode."""

    def __init__(
        self,
        screens,
        *,
        current_display: str | None = None,
        demo_mode: bool = False,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("TouchDeck setup")
        self.setModal(True)

        root = QVBoxLayout(self)
        root.setContentsMargins(18, 18, 18, 18)
        root.setSpacing(12)

        root.addWidget(QLabel("Choose which display TouchDeck should open on:"))

        self.display_picker = QComboBox()
        self._populate_displays(screens, current_display)
        root.addWidget(self.display_picker)

        self.demo_mode = QCheckBox("Demo mode (stay windowed instead of fullscreen)")
        self.demo_mode.setChecked(demo_mode)
        root.addWidget(self.demo_mode)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)

        btn_row = QHBoxLayout()
        btn_row.addStretch(1)
        btn_row.addWidget(buttons)
        root.addLayout(btn_row)

        self.setFixedWidth(320)

    def _populate_displays(self, screens, current_display: str | None) -> None:
        for s in screens:
            label = f"{s.name()} — {s.geometry().width()}x{s.geometry().height()}"
            self.display_picker.addItem(label, s.name())
        if current_display:
            idx = self.display_picker.findData(current_display)
            if idx >= 0:
                self.display_picker.setCurrentIndex(idx)

    def selected_display(self) -> str | None:
        return self.display_picker.currentData()

    def is_demo_mode(self) -> bool:
        return self.demo_mode.isChecked()
