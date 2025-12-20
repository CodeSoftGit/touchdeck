from __future__ import annotations

import asyncio
from dataclasses import dataclass
from time import monotonic

from PySide6.QtCore import Qt, QEvent, QTimer, QObject, QPointF, Slot
from PySide6.QtWidgets import QApplication, QWidget, QVBoxLayout, QStackedWidget, QAbstractSlider

from touchdeck.constants import WINDOW_W, WINDOW_H, CORNER_RADIUS
from touchdeck.ui.pages import MusicPage, StatsPage, ClockPage, SettingsPage, SpeedtestPage, EmojiPage
from touchdeck.ui.widgets import DotIndicator
from touchdeck.services.mpris import MprisService
from touchdeck.services.stats import StatsService
from touchdeck.services.speedtest import SpeedtestService
from touchdeck.settings import load_settings, save_settings, Settings
from touchdeck.themes import build_qss, get_theme, Theme


@dataclass
class _SwipeState:
    active: bool = False
    ignore: bool = False
    start_pos: QPointF | None = None
    start_t: float = 0.0


class SwipeNavigator(QObject):
    """Mouse/touch swipe detection that works on desktops and touchscreens.

    Qt's QSwipeGesture can be inconsistent depending on platform/device.
    This keeps it simple: drag horizontally enough, fast enough -> flip page.
    """

    def __init__(self, host: "DeckWindow") -> None:
        super().__init__(host)
        self.host = host
        self.s = _SwipeState()

        # Tune for 800x480-ish touch panels
        self.min_dx_px = 110
        self.max_dt_s = 0.85
        self.axis_bias = 1.35  # |dx| must be this much bigger than |dy|

    def eventFilter(self, obj, ev) -> bool:  # noqa: N802
        t = ev.type()

        if t == QEvent.MouseButtonPress and ev.button() == Qt.LeftButton:
            self._begin(ev.position(), self._should_ignore(obj, ev.position()))
            return False

        if t == QEvent.MouseButtonRelease and ev.button() == Qt.LeftButton:
            self._end(ev.position())
            return False

        if t == QEvent.TouchBegin:
            p = self._touch_pos(ev)
            self._begin(p, self._should_ignore(obj, p))
            return False

        if t in (QEvent.TouchEnd, QEvent.TouchCancel):
            p = self._touch_pos(ev)
            self._end(p)
            return False

        return False

    def _touch_pos(self, ev) -> QPointF:
        # Qt6 touch events expose points()
        pts = getattr(ev, "points", None)
        if callable(pts):
            ps = ev.points()
            if ps:
                return ps[0].position()
        # Fallback
        return QPointF(0, 0)

    def _should_ignore(self, obj, pos: QPointF) -> bool:
        # If the swipe starts on a slider (seeking), let the slider win.
        w = self.host.childAt(int(pos.x()), int(pos.y()))
        while w is not None:
            if isinstance(w, QAbstractSlider):
                return True
            # also ignore if user starts on a button (tap should click)
            if w.metaObject().className() in ("QPushButton", "QToolButton"):
                return True
            w = w.parentWidget()
        return False

    def _begin(self, pos: QPointF, ignore: bool) -> None:
        self.s.active = True
        self.s.ignore = ignore
        self.s.start_pos = pos
        self.s.start_t = monotonic()

    def _end(self, pos: QPointF) -> None:
        if not self.s.active:
            return
        self.s.active = False
        if self.s.ignore or self.s.start_pos is None:
            return

        dt = monotonic() - self.s.start_t
        dx = pos.x() - self.s.start_pos.x()
        dy = pos.y() - self.s.start_pos.y()

        if dt > self.max_dt_s:
            return
        if abs(dx) < self.min_dx_px:
            return
        if abs(dx) < abs(dy) * self.axis_bias:
            return

        if dx < 0:
            self.host.next_page()
        else:
            self.host.prev_page()


class DeckWindow(QWidget):
    def __init__(self, settings: Settings | None = None) -> None:
        super().__init__()
        self.setObjectName("DeckWindow")
        self.setWindowTitle("touchdeck")
        self.setFixedSize(WINDOW_W, WINDOW_H)
        self.setAttribute(Qt.WA_AcceptTouchEvents, True)
        self.setStyleSheet(f"border-radius: {CORNER_RADIUS}px;")

        self.settings = settings or load_settings()
        self._theme: Theme = get_theme(self.settings.theme)

        self._mpris = MprisService()
        self._stats = StatsService(enable_gpu=self.settings.enable_gpu_stats)
        self._speedtest = SpeedtestService()

        self.stack = QStackedWidget()
        self.page_music = MusicPage(self._theme)
        self.page_stats = StatsPage(self.settings, theme=self._theme)
        self.page_clock = ClockPage(self.settings, theme=self._theme)
        self.page_emoji = EmojiPage(theme=self._theme)
        self.page_speedtest = SpeedtestPage(self._on_speedtest_requested, theme=self._theme)
        self.page_settings = SettingsPage(self.settings, self._on_settings_changed, theme=self._theme)

        self.stack.addWidget(self.page_music)
        self.stack.addWidget(self.page_stats)
        self.stack.addWidget(self.page_clock)
        self.stack.addWidget(self.page_emoji)
        self.stack.addWidget(self.page_speedtest)
        self.stack.addWidget(self.page_settings)

        self.dots = DotIndicator(self.stack.count(), theme=self._theme)
        self.dots.set_index(0)

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 12)
        root.setSpacing(8)
        root.addWidget(self.stack, 1)
        root.addWidget(self.dots, 0)

        # swipe handler
        self._swipe = SwipeNavigator(self)
        # Install on window and the stack so it catches drags started anywhere
        self.installEventFilter(self._swipe)
        self.stack.installEventFilter(self._swipe)
        self.page_music.installEventFilter(self._swipe)
        self.page_stats.installEventFilter(self._swipe)
        self.page_clock.installEventFilter(self._swipe)
        self.page_emoji.installEventFilter(self._swipe)
        self.page_speedtest.installEventFilter(self._swipe)
        self.page_settings.installEventFilter(self._swipe)
        self.dots.installEventFilter(self._swipe)

        # wire music controls
        self.page_music.bind_controls(
            on_prev=self._on_prev,
            on_playpause=self._on_playpause,
            on_next=self._on_next,
            on_seek=self._on_seek,
        )

        # Poll timers
        self._timer_music = QTimer(self)
        self._timer_music.setInterval(self.settings.music_poll_ms)
        self._timer_music.timeout.connect(self._poll_music)
        self._timer_music.start()

        self._timer_stats = QTimer(self)
        self._timer_stats.setInterval(self.settings.stats_poll_ms)
        self._timer_stats.timeout.connect(self._poll_stats)
        self._timer_stats.start()

        self._apply_theme(self._theme)
        # apply initial settings now that timers exist
        self._apply_settings()

    # Public for SwipeNavigator
    def next_page(self) -> None:
        idx = (self.stack.currentIndex() + 1) % self.stack.count()
        self._set_page(idx)

    def prev_page(self) -> None:
        idx = (self.stack.currentIndex() - 1) % self.stack.count()
        self._set_page(idx)

    def _set_page(self, idx: int) -> None:
        self.stack.setCurrentIndex(idx)
        self.dots.set_index(idx)

    def _apply_settings(self) -> None:
        new_theme = get_theme(self.settings.theme)
        if new_theme.key != self._theme.key:
            self._theme = new_theme
            self._apply_theme(self._theme)

        # Opacity dimming disabled because some platforms render it incorrectly; we still
        # keep the value in settings for future use.
        self.page_stats.apply_settings(self.settings)
        self.page_clock.apply_settings(self.settings)
        self.page_settings.apply_settings(self.settings)
        self._stats.set_gpu_enabled(self.settings.enable_gpu_stats)
        self._timer_music.setInterval(self.settings.music_poll_ms)
        self._timer_stats.setInterval(self.settings.stats_poll_ms)

    def _apply_theme(self, theme: Theme) -> None:
        app = QApplication.instance()
        if app is not None:
            app.setStyleSheet(build_qss(theme))
        self.page_music.apply_theme(theme)
        self.page_stats.apply_theme(theme)
        self.page_clock.apply_theme(theme)
        self.page_emoji.apply_theme(theme)
        self.page_speedtest.apply_theme(theme)
        self.page_settings.apply_theme(theme)
        self.dots.apply_theme(theme)
        # Keep window border radius styling intact
        self.setStyleSheet(f"border-radius: {CORNER_RADIUS}px;")

    # ----- Poll + update UI -----
    @Slot()
    def _poll_music(self) -> None:
        asyncio.create_task(self._poll_music_async())

    async def _poll_music_async(self) -> None:
        np = await self._mpris.now_playing()
        self.page_music.set_now_playing(np)

    @Slot()
    def _poll_stats(self) -> None:
        s = self._stats.read()
        self.page_stats.set_stats(s)

    # ----- Control callbacks -----
    @Slot()
    def _on_playpause(self) -> None:
        asyncio.create_task(self._mpris_control("playpause"))

    @Slot()
    def _on_next(self) -> None:
        asyncio.create_task(self._mpris_control("next"))

    @Slot()
    def _on_prev(self) -> None:
        asyncio.create_task(self._mpris_control("prev"))

    def _on_seek(self, position_ms: int) -> None:
        asyncio.create_task(self._mpris_seek(position_ms))

    async def _mpris_control(self, action: str) -> None:
        np = await self._mpris.now_playing()
        if not np.bus_name:
            return
        if action == "playpause":
            await self._mpris.play_pause(np.bus_name)
        elif action == "next":
            await self._mpris.next(np.bus_name)
        elif action == "prev":
            await self._mpris.previous(np.bus_name)

    async def _mpris_seek(self, position_ms: int) -> None:
        np = await self._mpris.now_playing()
        if not (np.bus_name and np.can_seek and np.track_id):
            return
        await self._mpris.set_position(np.bus_name, np.track_id, position_ms)

    def _on_settings_changed(self, new_settings: Settings) -> None:
        self.settings = new_settings
        save_settings(self.settings)
        self._apply_settings()

    def _on_speedtest_requested(self) -> None:
        asyncio.create_task(self._run_speedtest())

    async def _run_speedtest(self) -> None:
        try:
            result = await self._speedtest.run()
        except Exception as exc:
            self.page_speedtest.show_error(str(exc))
            return
        self.page_speedtest.show_result(result)
