from __future__ import annotations

from PySide6.QtWidgets import QVBoxLayout, QWidget

from touchdeck.settings import Settings
from touchdeck.ui.widgets import Card, StatRow
from touchdeck.services.stats import Stats
from touchdeck.themes import Theme, get_theme


class StatsPage(QWidget):
    def __init__(
        self,
        settings: Settings,
        parent: QWidget | None = None,
        theme: Theme | None = None,
    ) -> None:
        super().__init__(parent)
        self._show_gpu = settings.enable_gpu_stats
        self._theme = theme or get_theme(settings.theme)
        self.card = Card(theme=self._theme)

        self.gpu = StatRow("GPU Usage", theme=self._theme)
        self.vram = StatRow("VRAM Usage", theme=self._theme)
        self.cpu = StatRow("CPU Usage", theme=self._theme)
        self.ram = StatRow("RAM Usage", theme=self._theme)

        self.card.body.addWidget(self.gpu)
        self.card.body.addWidget(self.vram)
        self.card.body.addWidget(self.cpu)
        self.card.body.addWidget(self.ram)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(26, 26, 26, 26)
        lay.addWidget(self.card)

        self.apply_settings(settings)

    def set_stats(self, s: Stats) -> None:
        if self._show_gpu and s.gpu_percent is not None:
            self.gpu.set_percent(s.gpu_percent, f"{s.gpu_percent:.0f}%")
            if s.vram_percent is None or s.vram_used_gb is None:
                self.vram.set_percent(0, "N/A")
            else:
                self.vram.set_percent(s.vram_percent, f"{s.vram_used_gb:.1f} GB")
        else:
            self.gpu.set_percent(0, "N/A")
            self.vram.set_percent(0, "N/A")

        self.cpu.set_percent(s.cpu_percent, f"{s.cpu_percent:.0f}%")
        self.ram.set_percent(s.ram_percent, f"{s.ram_used_gb:.1f} GB")

    def apply_settings(self, settings: Settings) -> None:
        self._show_gpu = settings.enable_gpu_stats
        self.gpu.setVisible(self._show_gpu)
        self.vram.setVisible(self._show_gpu)

    def apply_theme(self, theme: Theme) -> None:
        self._theme = theme
        self.card.apply_theme(theme)
        for row in (self.gpu, self.vram, self.cpu, self.ram):
            row.apply_theme(theme)
