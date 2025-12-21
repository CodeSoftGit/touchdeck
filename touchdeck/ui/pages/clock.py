from __future__ import annotations

import datetime

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import QLabel, QVBoxLayout, QWidget

from touchdeck.settings import Settings
from touchdeck.ui.widgets import Card
from touchdeck.themes import Theme, get_theme


class ClockPage(QWidget):
    def __init__(
        self,
        settings: Settings,
        parent: QWidget | None = None,
        theme: Theme | None = None,
    ) -> None:
        super().__init__(parent)
        self._theme = theme or get_theme(settings.theme)
        self._clock_24h = settings.clock_24h
        self._show_seconds = settings.show_clock_seconds
        self.card = Card(theme=self._theme)

        self.time = QLabel("00:00")
        self.time.setStyleSheet("font-size: 110px; font-weight: 650;")
        self.time.setAlignment(Qt.AlignCenter)

        self.ampm = QLabel("AM")
        self.ampm.setObjectName("Subtle")
        self.ampm.setStyleSheet("font-size: 28px;")
        self.ampm.setAlignment(Qt.AlignCenter)

        self.card.body.addStretch(1)
        self.card.body.addWidget(self.time)
        self.card.body.addWidget(self.ampm)
        self.card.body.addStretch(1)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(26, 26, 26, 26)
        lay.addWidget(self.card)

        self._timer = QTimer(self)
        self._timer.setInterval(250)
        self._timer.timeout.connect(self._tick)
        self._timer.start()
        self._tick()

    def _tick(self) -> None:
        now = datetime.datetime.now()
        if self._clock_24h:
            fmt = "%H:%M:%S" if self._show_seconds else "%H:%M"
            self.time.setText(now.strftime(fmt))
            self.ampm.setText("" if self._show_seconds else "")
        else:
            fmt = "%I:%M:%S" if self._show_seconds else "%I:%M"
            self.time.setText(now.strftime(fmt).lstrip("0") or "0")
            self.ampm.setText("" if self._show_seconds else now.strftime("%p"))

    def apply_settings(self, settings: Settings) -> None:
        self._clock_24h = settings.clock_24h
        self._show_seconds = settings.show_clock_seconds
        self._tick()

    def apply_theme(self, theme: Theme) -> None:
        self._theme = theme
        self.card.apply_theme(theme)
