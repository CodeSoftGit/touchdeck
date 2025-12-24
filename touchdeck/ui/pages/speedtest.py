from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget

from touchdeck.services.speedtest import SpeedtestResult
from touchdeck.themes import Theme, get_theme
from touchdeck.ui.widgets import Card


class SpeedtestPage(QWidget):
    def __init__(
        self, on_run, parent: QWidget | None = None, theme: Theme | None = None
    ) -> None:
        super().__init__(parent)
        self._on_run = on_run
        self._theme = theme or get_theme(None)
        self.card = Card(theme=self._theme)

        title = QLabel("Speed Test")
        title.setStyleSheet("font-size: 28px; font-weight: 700;")

        self.status = QLabel("Tap run to measure")
        self.status.setObjectName("Subtle")
        self.status.setStyleSheet("font-size: 16px;")

        self.down = QLabel("--")
        self.up = QLabel("--")
        self.ping = QLabel("--")
        for lbl in (self.down, self.up, self.ping):
            lbl.setStyleSheet("font-size: 34px; font-weight: 750;")
            lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)

        def caption(text: str) -> QLabel:
            lab = QLabel(text)
            lab.setObjectName("Subtle")
            lab.setStyleSheet("font-size: 16px;")
            lab.setAlignment(Qt.AlignmentFlag.AlignCenter)
            return lab

        row = QHBoxLayout()
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(18)

        col_down = QVBoxLayout()
        col_down.setContentsMargins(0, 0, 0, 0)
        col_down.setSpacing(4)
        col_down.addWidget(self.down)
        col_down.addWidget(caption("Download (Mbps)"))

        col_up = QVBoxLayout()
        col_up.setContentsMargins(0, 0, 0, 0)
        col_up.setSpacing(4)
        col_up.addWidget(self.up)
        col_up.addWidget(caption("Upload (Mbps)"))

        col_ping = QVBoxLayout()
        col_ping.setContentsMargins(0, 0, 0, 0)
        col_ping.setSpacing(4)
        col_ping.addWidget(self.ping)
        col_ping.addWidget(caption("Ping (ms)"))

        row.addLayout(col_down, 1)
        row.addLayout(col_up, 1)
        row.addLayout(col_ping, 1)

        self.btn_run = QPushButton("Run speed test")
        self.btn_run.setCursor(Qt.CursorShape.PointingHandCursor)
        self._apply_button_theme()
        self.btn_run.clicked.connect(self._on_run_clicked)

        self.card.body.addWidget(title)
        self.card.body.addWidget(self.status)
        self.card.body.addSpacing(8)
        self.card.body.addLayout(row)
        self.card.body.addSpacing(12)
        self.card.body.addWidget(self.btn_run, alignment=Qt.AlignmentFlag.AlignCenter)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(26, 26, 26, 26)
        lay.addWidget(self.card)

    def _on_run_clicked(self) -> None:
        if callable(self._on_run):
            self.set_running(True)
            self._on_run()

    def set_running(self, running: bool) -> None:
        self.btn_run.setDisabled(running)
        if running:
            self.status.setText("Running test…")
        else:
            self.status.setText("Tap run to measure")

    def show_result(self, result: SpeedtestResult) -> None:
        self.set_running(False)
        self.down.setText(f"{result.download_mbps:.1f}")
        self.up.setText(f"{result.upload_mbps:.1f}")
        self.ping.setText(f"{result.ping_ms:.0f}")
        self.status.setText("Measured just now")

    def show_error(self, message: str) -> None:
        self.set_running(False)
        self.status.setText(message)
        self.down.setText("--")
        self.up.setText("--")
        self.ping.setText("--")

    def apply_theme(self, theme: Theme) -> None:
        self._theme = theme
        self.card.apply_theme(theme)
        self._apply_button_theme()

    def _apply_button_theme(self) -> None:
        self.btn_run.setStyleSheet(
            f"""
            QPushButton {{
                font-size: 18px;
                font-weight: 650;
                padding: 14px 18px;
                border-radius: 14px;
                background: {self._theme.accent};
                color: {self._theme.background};
            }}
            QPushButton:disabled {{
                background: {self._theme.neutral};
                color: {self._theme.subtle};
            }}
            QPushButton:pressed {{
                background: {self._theme.accent_pressed};
            }}
            """
        )
