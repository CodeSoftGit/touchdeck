from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QLabel, QGridLayout, QVBoxLayout, QWidget

from touchdeck.settings import Settings
from touchdeck.ui.widgets import Card
from touchdeck.themes import Theme, get_theme


class DeveloperPage(QWidget):
    def __init__(
        self,
        settings: Settings,
        parent: QWidget | None = None,
        theme: Theme | None = None,
    ) -> None:
        super().__init__(parent)
        self._theme = theme or get_theme(settings.theme)
        self.card = Card(theme=self._theme)

        title = QLabel("Developer")
        title.setStyleSheet("font-size: 28px; font-weight: 700;")

        self._theme_value = QLabel()
        self._scale_value = QLabel()
        self._opacity_value = QLabel()
        self._demo_value = QLabel()
        self._gpu_value = QLabel()
        self._error_count = QLabel("0")
        self._warning_count = QLabel("0")
        self._pages_value = QLabel()
        self._pages_value.setWordWrap(True)
        self._logs_value = QLabel("No warnings or errors yet.")
        self._logs_value.setObjectName("Subtle")
        self._logs_value.setWordWrap(True)
        self._logs_value.setStyleSheet("font-size: 14px;")

        info = QGridLayout()
        info.setContentsMargins(0, 0, 0, 0)
        info.setHorizontalSpacing(16)
        info.setVerticalSpacing(8)

        self._add_info_row(info, 0, "Theme", self._theme_value)
        self._add_info_row(info, 1, "UI scale", self._scale_value)
        self._add_info_row(info, 2, "Brightness", self._opacity_value)
        self._add_info_row(info, 3, "Demo mode", self._demo_value)
        self._add_info_row(info, 4, "GPU stats", self._gpu_value)
        self._add_info_row(info, 5, "Errors", self._error_count)
        self._add_info_row(info, 6, "Warnings", self._warning_count)
        self._add_info_row(info, 7, "Enabled pages", self._pages_value)

        self.card.body.addWidget(title)
        self.card.body.addSpacing(12)
        self.card.body.addLayout(info)
        self.card.body.addSpacing(16)
        self.card.body.addWidget(QLabel("Recent warnings/errors"))
        self.card.body.addWidget(self._logs_value)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(26, 26, 26, 26)
        lay.addWidget(self.card)

        self.apply_settings(settings)

    @staticmethod
    def _add_info_row(
        layout: QGridLayout, row: int, label: str, value: QLabel
    ) -> None:
        name = QLabel(label)
        name.setObjectName("Subtle")
        name.setStyleSheet("font-size: 16px;")
        value.setStyleSheet("font-size: 16px;")
        layout.addWidget(name, row, 0, Qt.AlignTop)
        layout.addWidget(value, row, 1, Qt.AlignTop)

    def apply_settings(self, settings: Settings) -> None:
        self._theme_value.setText(settings.theme)
        self._scale_value.setText(f"{settings.ui_scale_percent}%")
        self._opacity_value.setText(f"{settings.ui_opacity_percent}%")
        self._demo_value.setText("On" if settings.demo_mode else "Off")
        self._gpu_value.setText("On" if settings.enable_gpu_stats else "Off")
        self._pages_value.setText(", ".join(settings.enabled_pages))

    def apply_theme(self, theme: Theme) -> None:
        self._theme = theme
        self.card.apply_theme(theme)

    def set_events(self, events: list[dict[str, str]]) -> None:
        errors = [e for e in events if e.get("level") == "ERROR"]
        warnings = [e for e in events if e.get("level") == "WARN"]
        self._error_count.setText(str(len(errors)))
        self._warning_count.setText(str(len(warnings)))
        if not events:
            self._logs_value.setText("No warnings or errors yet.")
            return
        recent = list(reversed(events))[:6]
        lines = []
        for entry in recent:
            timestamp = entry.get("time", "--:--:--")
            level = entry.get("level", "INFO")
            source = entry.get("source", "unknown")
            message = entry.get("message", "")
            lines.append(f"{timestamp} {level} {source}: {message}")
        self._logs_value.setText("\n".join(lines))
