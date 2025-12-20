from __future__ import annotations

import datetime
from typing import Callable

from functools import partial
from pathlib import Path

from PySide6.QtCore import Qt, QTimer, QUrl, QSize
from PySide6.QtGui import QPixmap, QPainter, QPainterPath, QGuiApplication, QIcon
from PySide6.QtNetwork import QNetworkAccessManager, QNetworkRequest
from PySide6.QtWidgets import (
    QWidget,
    QLabel,
    QHBoxLayout,
    QVBoxLayout,
    QSlider,
    QPushButton,
    QScrollArea,
    QFrame,
    QComboBox,
    QGridLayout,
)

from touchdeck.settings import Settings
from touchdeck.services.speedtest import SpeedtestResult
from touchdeck.utils import NowPlaying, ms_to_mmss
from touchdeck.ui.widgets import Card, IconButton, StatRow, ElideLabel
from touchdeck.services.stats import Stats
from touchdeck.themes import Theme, DEFAULT_THEME_KEY, get_theme, theme_options


def _rounded_pixmap(src: QPixmap, size: int, radius: int) -> QPixmap:
    if src.isNull():
        return QPixmap()
    scaled = src.scaled(size, size, Qt.KeepAspectRatioByExpanding, Qt.SmoothTransformation)
    out = QPixmap(size, size)
    out.fill(Qt.transparent)
    p = QPainter(out)
    p.setRenderHint(QPainter.Antialiasing, True)
    path = QPainterPath()
    path.addRoundedRect(0, 0, size, size, radius, radius)
    p.setClipPath(path)
    p.drawPixmap(0, 0, scaled)
    p.end()
    return out


class ToggleRow(QWidget):
    """Touch-friendly toggle button row with obvious on/off state."""

    def __init__(
        self,
        title: str,
        *,
        initial: bool = False,
        on_change: Callable[[bool], None] | None = None,
        parent: QWidget | None = None,
        theme: Theme | None = None,
    ) -> None:
        super().__init__(parent)
        self._title = title
        self._on_change = on_change
        self._theme = theme or get_theme(None)
        self._btn = QPushButton()
        self._btn.setCheckable(True)
        self._btn.setChecked(initial)
        self._btn.setCursor(Qt.PointingHandCursor)
        self._btn.clicked.connect(self._on_clicked)
        self._apply_theme()

        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.addWidget(self._btn)

        self._update_text()

    def _on_clicked(self) -> None:
        self._update_text()
        if self._on_change is not None:
            self._on_change(self._btn.isChecked())

    def _update_text(self) -> None:
        state = "On" if self._btn.isChecked() else "Off"
        self._btn.setText(f"{self._title} · {state}")

    def set_checked(self, checked: bool) -> None:
        self._btn.setChecked(checked)
        self._update_text()

    def is_checked(self) -> bool:
        return self._btn.isChecked()

    def apply_theme(self, theme: Theme) -> None:
        self._theme = theme
        self._apply_theme()

    def _apply_theme(self) -> None:
        self._btn.setStyleSheet(
            f"""
            QPushButton {{
                font-size: 18px;
                font-weight: 650;
                padding: 14px 16px;
                border-radius: 14px;
                text-align: left;
                background: {self._theme.neutral};
                color: {self._theme.text};
            }}
            QPushButton:checked {{
                background: {self._theme.accent};
                color: {self._theme.background};
            }}
            QPushButton:pressed {{
                background: {self._theme.accent_pressed};
            }}
            """
        )


class DragScrollArea(QScrollArea):
    """Scroll area that supports mouse/touch dragging to scroll."""

    def __init__(self, parent: QWidget | None = None, theme: Theme | None = None) -> None:
        super().__init__(parent)
        self._theme = theme or get_theme(None)
        self._dragging = False
        self._last_y = 0.0
        self.setWidgetResizable(True)
        self.setFrameShape(QFrame.NoFrame)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self._apply_style()

    def mousePressEvent(self, ev) -> None:
        if ev.button() == Qt.LeftButton:
            self._dragging = True
            self._last_y = ev.position().y()
        super().mousePressEvent(ev)

    def mouseMoveEvent(self, ev) -> None:
        if self._dragging:
            dy = ev.position().y() - self._last_y
            self._last_y = ev.position().y()
            bar = self.verticalScrollBar()
            bar.setValue(bar.value() - int(dy))
        super().mouseMoveEvent(ev)

    def mouseReleaseEvent(self, ev) -> None:
        if ev.button() == Qt.LeftButton:
            self._dragging = False
        super().mouseReleaseEvent(ev)

    def apply_theme(self, theme: Theme) -> None:
        self._theme = theme
        self._apply_style()

    def _apply_style(self) -> None:
        self.setStyleSheet(
            f"""
            QScrollArea {{
                background: transparent;
            }}
            QScrollBar:vertical {{
                background: transparent;
                width: 12px;
                margin: 8px 4px 8px 0px;
            }}
            QScrollBar::handle:vertical {{
                background: {self._theme.neutral_hover};
                border-radius: 6px;
                min-height: 36px;
            }}
            QScrollBar::handle:vertical:pressed {{
                background: {self._theme.neutral_pressed};
            }}
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
                height: 0px;
            }}
            QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{
                background: transparent;
            }}
            """
        )


class MusicPage(QWidget):
    def __init__(self, theme: Theme, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._theme = theme
        self._np: NowPlaying | None = None
        self._seeking = False

        self._net = QNetworkAccessManager(self)
        self._net.finished.connect(self._on_art_reply)

        self.card = Card(theme=theme)

        # artwork
        self.art = QLabel()
        self.art_size = 156
        self.art_radius = 20
        self.art.setFixedSize(self.art_size, self.art_size)
        self.art.setAlignment(Qt.AlignCenter)
        self.art.setText("♪")
        self._apply_art_style()

        # text
        self.title = ElideLabel("Nothing Playing", mode=Qt.ElideRight)
        self.title.setStyleSheet("font-size: 34px; font-weight: 750;")
        self.title.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)

        self.artist = ElideLabel("", mode=Qt.ElideRight)
        self.artist.setObjectName("Subtle")
        self.artist.setStyleSheet("font-size: 18px;")
        self.artist.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)

        # layout: art left, text right
        header = QHBoxLayout()
        header.setContentsMargins(0, 0, 0, 0)
        header.setSpacing(22)
        header.addWidget(self.art, 0, Qt.AlignVCenter)

        text_col = QVBoxLayout()
        text_col.setContentsMargins(0, 0, 0, 0)
        text_col.setSpacing(6)
        text_col.addWidget(self.title)
        text_col.addWidget(self.artist)
        text_col.addStretch(1)
        header.addLayout(text_col, 1)

        # slider + times
        self.slider = QSlider(Qt.Horizontal)
        self.slider.setRange(0, 1000)
        self.slider.sliderPressed.connect(self._on_slider_pressed)
        self.slider.sliderReleased.connect(self._on_slider_released)

        self.t_left = QLabel("0:00")
        self.t_left.setObjectName("Subtle")
        self.t_right = QLabel("0:00")
        self.t_right.setObjectName("Subtle")
        self.t_right.setAlignment(Qt.AlignRight | Qt.AlignVCenter)

        time_row = QHBoxLayout()
        time_row.setContentsMargins(0, 0, 0, 0)
        time_row.addWidget(self.t_left, 1)
        time_row.addWidget(self.t_right, 1)

        # controls
        self.btn_prev = IconButton("prev", diameter=46, filled=False, theme=self._theme)
        self.btn_play = IconButton("play", diameter=70, filled=True, theme=self._theme)
        self.btn_next = IconButton("next", diameter=46, filled=False, theme=self._theme)

        ctr = QHBoxLayout()
        ctr.setContentsMargins(0, 0, 0, 0)
        ctr.setSpacing(18)
        ctr.addStretch(1)
        ctr.addWidget(self.btn_prev)
        ctr.addWidget(self.btn_play)
        ctr.addWidget(self.btn_next)
        ctr.addStretch(1)

        self.card.body.addLayout(header)
        self.card.body.addSpacing(12)
        self.card.body.addWidget(self.slider)
        self.card.body.addLayout(time_row)
        self.card.body.addSpacing(12)
        self.card.body.addLayout(ctr)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(26, 26, 26, 26)
        lay.addWidget(self.card)

        self._current_art_url: str | None = None

    def bind_controls(self, on_prev, on_playpause, on_next, on_seek) -> None:
        self.btn_prev.clicked.connect(on_prev)
        self.btn_play.clicked.connect(on_playpause)
        self.btn_next.clicked.connect(on_next)
        self._on_seek = on_seek

    def apply_theme(self, theme: Theme) -> None:
        self._theme = theme
        self.card.apply_theme(theme)
        self.btn_prev.set_theme(theme)
        self.btn_play.set_theme(theme)
        self.btn_next.set_theme(theme)
        self._apply_art_style()
        self.update()

    def set_now_playing(self, np: NowPlaying) -> None:
        self._np = np

        # More "deck-y": keep text stable, avoid flickering empty
        self.title.setText(np.title or "Nothing Playing")
        self.artist.setText(np.artist or "")

        # Update play/pause icon
        self.btn_play.kind = "pause" if np.status == "Playing" else "play"
        self.btn_play.update()

        # Update slider
        length = max(1, int(np.length_ms or 1))
        self.slider.setRange(0, length)
        if not self._seeking:
            self.slider.setValue(int(np.position_ms or 0))

        self.t_left.setText(ms_to_mmss(int(np.position_ms or 0)))
        self.t_right.setText(ms_to_mmss(int(np.length_ms or 0)))

        # Artwork
        self._set_art(np.art_url)

    def _set_art(self, url: str | None) -> None:
        if not url:
            self._current_art_url = None
            self.art.setPixmap(QPixmap())
            self.art.setText("♪")
            return

        if url == self._current_art_url:
            return
        self._current_art_url = url

        qurl = QUrl(url)
        if qurl.isLocalFile() or url.startswith("file://"):
            path = qurl.toLocalFile()
            pix = QPixmap(path)
            self._apply_pix(pix)
        else:
            self._net.get(QNetworkRequest(qurl))

    def _on_art_reply(self, reply) -> None:
        if reply.error():
            return
        data = reply.readAll()
        pix = QPixmap()
        pix.loadFromData(bytes(data))
        self._apply_pix(pix)

    def _apply_pix(self, pix: QPixmap) -> None:
        if pix.isNull():
            self.art.setPixmap(QPixmap())
            self.art.setText("♪")
            return
        rounded = _rounded_pixmap(pix, self.art_size, self.art_radius)
        self.art.setPixmap(rounded)
        self.art.setText("")

    def _apply_art_style(self) -> None:
        self.art.setStyleSheet(
            f"font-size: 46px; border-radius: {self.art_radius}px; background: {self._theme.neutral};"
        )

    def _on_slider_pressed(self) -> None:
        self._seeking = True

    def _on_slider_released(self) -> None:
        self._seeking = False
        if not self._np:
            return
        if not getattr(self, "_on_seek", None):
            return
        self._on_seek(self.slider.value())


class EmojiPage(QWidget):
    _EMOJIS: list[tuple[str, str | None]] = [
        ("😀", "emoji_u1f600.svg"),
        ("😂", "emoji_u1f602.svg"),
        ("😉", "emoji_u1f609.svg"),
        ("😍", "emoji_u1f60d.svg"),
        ("😮", "emoji_u1f62e.svg"),
        ("ಠ_ಠ", None),
        ("🥀", "emoji_u1f940.svg"),
        (":3", None),
        ("🔥", "emoji_u1f525.svg"),
        ("✨", "emoji_u2728.svg"),
        ("🎉", "emoji_u1f389.svg"),
        (":)", None),
        ("(ㆆ _ ㆆ)", None),
        ("🎁", "emoji_u1f381.svg"),
        ("( ͡° ͜ʖ ͡°)", None),
        ("¯\\_(ツ)_/¯", None),
    ]

    def __init__(self, parent: QWidget | None = None, theme: Theme | None = None) -> None:
        super().__init__(parent)
        self._theme = theme or get_theme(None)
        self.card = Card(theme=self._theme)
        self._buttons: list[QPushButton] = []
        self._emoji_root = Path(__file__).resolve().parent.parent / "emojis"
        self._toast = QLabel(self)
        self._toast.setVisible(False)
        self._toast.setStyleSheet(
            """
            QLabel {
                background: rgba(0, 0, 0, 180);
                color: white;
                padding: 10px 14px;
                border-radius: 12px;
                font-weight: 650;
                font-size: 16px;
            }
            """
        )
        self._toast.setAttribute(Qt.WA_TransparentForMouseEvents, True)

        # bare grid of emoji-only buttons
        grid = QGridLayout()
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setHorizontalSpacing(12)
        grid.setVerticalSpacing(12)

        cols = 4
        row = col = 0
        for emoji, filename in self._EMOJIS:
            icon = self._icon_for_file(filename)
            btn = QPushButton()
            btn.setFixedSize(74, 74)
            btn.setCursor(Qt.PointingHandCursor)
            if not icon.isNull():
                btn.setIcon(icon)
                btn.setIconSize(QSize(48, 48))
            else:
                btn.setText(emoji)
            btn.setToolTip(emoji)
            btn.setAccessibleName(emoji)
            btn.clicked.connect(partial(self._on_emoji_clicked, emoji))
            self._style_button(btn)
            self._buttons.append(btn)
            grid.addWidget(btn, row, col)
            col += 1
            if col >= cols:
                col = 0
                row += 1

        self.card.body.addLayout(grid)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(26, 26, 26, 26)
        lay.addWidget(self.card)

    def _on_emoji_clicked(self, emoji: str) -> None:
        QGuiApplication.clipboard().setText(emoji)
        self._show_toast(f"Copied {emoji}")

    def apply_theme(self, theme: Theme) -> None:
        self._theme = theme
        self.card.apply_theme(theme)
        for btn in self._buttons:
            self._style_button(btn)
        self.update()

    def _icon_for_file(self, filename: str | None) -> QIcon:
        if not filename:
            return QIcon()
        path = self._emoji_root / filename
        if not path.exists():
            return QIcon()
        return QIcon(str(path))

    def _show_toast(self, text: str, duration_ms: int = 1600) -> None:
        self._toast.setText(text)
        self._toast.adjustSize()
        self._position_toast()
        self._toast.show()
        self._toast.raise_()
        QTimer.singleShot(duration_ms, self._toast.hide)

    def _position_toast(self) -> None:
        if not self._toast.isVisible() and not self._toast.text():
            return
        x = max(0, (self.width() - self._toast.width()) // 2)
        y = max(0, self.height() - self._toast.height() - 20)
        self._toast.move(x, y)

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        if self._toast.isVisible():
            self._position_toast()

    def _style_button(self, btn: QPushButton) -> None:
        btn.setStyleSheet(
            f"""
            QPushButton {{
                font-size: 32px;
                font-weight: 500;
                padding: 0px;
                border: none;
                background: transparent;
                color: {self._theme.text};
            }}
            """
        )


class SettingsPage(QWidget):
    def __init__(self, settings: Settings, on_change, parent: QWidget | None = None, theme: Theme | None = None) -> None:
        super().__init__(parent)
        self._on_change = on_change
        self._settings = settings
        self._theme = theme or get_theme(settings.theme)
        self._syncing = False
        self.card = Card(theme=self._theme)

        title = QLabel("Settings")
        title.setStyleSheet("font-size: 28px; font-weight: 700;")

        # Toggles sized for touch
        self.toggle_gpu = ToggleRow("Enable GPU stats", initial=settings.enable_gpu_stats, on_change=self._emit_change, theme=self._theme)
        self.toggle_clock = ToggleRow("24-hour clock", initial=settings.clock_24h, on_change=self._emit_change, theme=self._theme)
        self.toggle_seconds = ToggleRow("Show seconds on clock", initial=settings.show_clock_seconds, on_change=self._emit_change, theme=self._theme)

        # Theme selector
        theme_row = QHBoxLayout()
        theme_row.setContentsMargins(0, 0, 0, 0)
        theme_row.addWidget(QLabel("Color theme"), 1)
        self.theme_picker = QComboBox()
        for opt in theme_options():
            self.theme_picker.addItem(opt.label, opt.key)
        self.theme_picker.currentIndexChanged.connect(self._emit_change)
        theme_row.addWidget(self.theme_picker, 0)

        # Brightness control
        bright_row = QHBoxLayout()
        bright_row.setContentsMargins(0, 0, 0, 0)
        bright_row.addWidget(QLabel("Brightness"), 1)
        self.brightness_value = QLabel("70%")
        self.brightness_value.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        self.brightness_value.setObjectName("Subtle")
        bright_row.addWidget(self.brightness_value, 0)

        self.brightness = QSlider(Qt.Horizontal)
        self.brightness.setRange(0, 100)
        self.brightness.valueChanged.connect(self._on_brightness_change)

        # Poll intervals
        self.music_poll_value = QLabel("0 ms")
        self.music_poll_value.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        self.music_poll_value.setObjectName("Subtle")
        music_row = QHBoxLayout()
        music_row.setContentsMargins(0, 0, 0, 0)
        music_row.addWidget(QLabel("Music refresh"), 1)
        music_row.addWidget(self.music_poll_value, 0)

        self.music_poll = QSlider(Qt.Horizontal)
        self.music_poll.setRange(250, 3000)
        self.music_poll.valueChanged.connect(self._on_poll_change)

        self.stats_poll_value = QLabel("0 ms")
        self.stats_poll_value.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        self.stats_poll_value.setObjectName("Subtle")
        stats_row = QHBoxLayout()
        stats_row.setContentsMargins(0, 0, 0, 0)
        stats_row.addWidget(QLabel("Stats refresh"), 1)
        stats_row.addWidget(self.stats_poll_value, 0)

        self.stats_poll = QSlider(Qt.Horizontal)
        self.stats_poll.setRange(500, 5000)
        self.stats_poll.valueChanged.connect(self._on_poll_change)

        self.card.body.addWidget(title)
        self.card.body.addSpacing(10)
        self.card.body.addWidget(self._section_title("General"))
        self.card.body.addWidget(self.toggle_gpu)
        self.card.body.addWidget(self.toggle_clock)
        self.card.body.addWidget(self.toggle_seconds)
        self.card.body.addSpacing(6)
        self.card.body.addLayout(theme_row)
        self.card.body.addSpacing(14)
        self.card.body.addWidget(self._section_title("Display"))
        self.card.body.addLayout(bright_row)
        self.card.body.addWidget(self.brightness)
        self.card.body.addSpacing(12)
        self.card.body.addWidget(self._section_title("Refresh"))
        self.card.body.addLayout(music_row)
        self.card.body.addWidget(self.music_poll)
        self.card.body.addLayout(stats_row)
        self.card.body.addWidget(self.stats_poll)

        content = QWidget()
        content_lay = QVBoxLayout(content)
        content_lay.setContentsMargins(26, 26, 26, 26)
        content_lay.addWidget(self.card)

        scroll = DragScrollArea(theme=self._theme)
        scroll.setWidget(content)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.addWidget(scroll)

        self.apply_settings(settings)

    def apply_settings(self, settings: Settings) -> None:
        self._syncing = True
        self._settings = settings
        self.toggle_gpu.set_checked(settings.enable_gpu_stats)
        self.toggle_clock.set_checked(settings.clock_24h)
        self.toggle_seconds.set_checked(settings.show_clock_seconds)
        self._set_theme_picker(settings.theme)
        self.brightness.blockSignals(True)
        self.brightness.setValue(settings.ui_opacity_percent)
        self.brightness.blockSignals(False)
        self._on_brightness_change(settings.ui_opacity_percent)
        self.music_poll.blockSignals(True)
        self.music_poll.setValue(settings.music_poll_ms)
        self.music_poll.blockSignals(False)
        self.stats_poll.blockSignals(True)
        self.stats_poll.setValue(settings.stats_poll_ms)
        self.stats_poll.blockSignals(False)
        self._update_poll_labels(settings.music_poll_ms, settings.stats_poll_ms)
        self._syncing = False

    def _on_brightness_change(self, value: int) -> None:
        self.brightness_value.setText(f"{value}%")
        self._emit_change()

    def _emit_change(self, *_args) -> None:
        if self._syncing:
            return
        new_settings = Settings(
            enable_gpu_stats=self.toggle_gpu.is_checked(),
            clock_24h=self.toggle_clock.is_checked(),
            show_clock_seconds=self.toggle_seconds.is_checked(),
            music_poll_ms=self.music_poll.value(),
            stats_poll_ms=self.stats_poll.value(),
            ui_opacity_percent=self.brightness.value(),
            theme=self.theme_picker.currentData() or DEFAULT_THEME_KEY,
        )
        if callable(self._on_change):
            self._on_change(new_settings)

    def _on_poll_change(self, value: int) -> None:
        self._update_poll_labels(self.music_poll.value(), self.stats_poll.value())
        self._emit_change()

    def _update_poll_labels(self, music_ms: int, stats_ms: int) -> None:
        self.music_poll_value.setText(f"{music_ms} ms")
        self.stats_poll_value.setText(f"{stats_ms} ms")

    def _set_theme_picker(self, key: str) -> None:
        idx = self.theme_picker.findData(key)
        if idx < 0:
            idx = self.theme_picker.findData(DEFAULT_THEME_KEY)
        if idx >= 0:
            self.theme_picker.blockSignals(True)
            self.theme_picker.setCurrentIndex(idx)
            self.theme_picker.blockSignals(False)

    def apply_theme(self, theme: Theme) -> None:
        self._theme = theme
        self.card.apply_theme(theme)
        self.toggle_gpu.apply_theme(theme)
        self.toggle_clock.apply_theme(theme)
        self.toggle_seconds.apply_theme(theme)
        self._style_sliders()
        self._style_theme_picker()

    def _style_sliders(self) -> None:
        # Make sliders chunkier for touch
        slider_style = f"""
            QSlider::groove:horizontal {{
                height: 12px;
                border-radius: 6px;
            }}
            QSlider::handle:horizontal {{
                width: 26px;
                height: 26px;
                margin: -7px 0;
                border-radius: 13px;
                background: {self._theme.slider_handle};
            }}
        """
        for sl in (self.brightness, self.music_poll, self.stats_poll):
            sl.setStyleSheet(slider_style)

    def _style_theme_picker(self) -> None:
        self.theme_picker.setStyleSheet(
            f"""
            QComboBox {{
                font-size: 18px;
                padding: 12px 14px;
                border-radius: 12px;
                background: {self._theme.neutral};
                color: {self._theme.text};
            }}
            QComboBox::drop-down {{
                width: 26px;
            }}
            QComboBox QAbstractItemView {{
                background: {self._theme.panel};
                color: {self._theme.text};
                selection-background-color: {self._theme.accent};
                selection-color: {self._theme.background};
            }}
            """
        )

    def _section_title(self, text: str) -> QLabel:
        lbl = QLabel(text)
        lbl.setObjectName("Subtle")
        lbl.setStyleSheet("font-size: 16px; font-weight: 650; padding-top: 4px;")
        return lbl


class StatsPage(QWidget):
    def __init__(self, settings: Settings, parent: QWidget | None = None, theme: Theme | None = None) -> None:
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


class ClockPage(QWidget):
    def __init__(self, settings: Settings, parent: QWidget | None = None, theme: Theme | None = None) -> None:
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


class SpeedtestPage(QWidget):
    def __init__(self, on_run, parent: QWidget | None = None, theme: Theme | None = None) -> None:
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
            lbl.setAlignment(Qt.AlignCenter)

        def caption(text: str) -> QLabel:
            lab = QLabel(text)
            lab.setObjectName("Subtle")
            lab.setStyleSheet("font-size: 16px;")
            lab.setAlignment(Qt.AlignCenter)
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
        self.btn_run.setCursor(Qt.PointingHandCursor)
        self._apply_button_theme()
        self.btn_run.clicked.connect(self._on_run_clicked)

        self.card.body.addWidget(title)
        self.card.body.addWidget(self.status)
        self.card.body.addSpacing(8)
        self.card.body.addLayout(row)
        self.card.body.addSpacing(12)
        self.card.body.addWidget(self.btn_run, alignment=Qt.AlignCenter)

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
