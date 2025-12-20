from __future__ import annotations

import asyncio
from dataclasses import dataclass, replace
import sys
from time import monotonic

from PySide6.QtCore import Qt, QEvent, QTimer, QObject, QPointF, Slot, QProcess
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication, QWidget, QVBoxLayout, QStackedWidget, QAbstractSlider

from touchdeck.constants import WINDOW_W, WINDOW_H, CORNER_RADIUS
from touchdeck.ui.pages import MusicPage, StatsPage, ClockPage, SettingsPage, SpeedtestPage, EmojiPage
from touchdeck.ui.widgets import DotIndicator, QuickActionsDrawer, OnboardingOverlay, NotificationStack, StartupOverlay
from touchdeck.services.mpris import MprisService
from touchdeck.services.stats import StatsService
from touchdeck.services.speedtest import SpeedtestService
from touchdeck.services.notifications import NotificationListener, SystemNotification
from touchdeck.settings import load_settings, save_settings, reset_settings, Settings, DEFAULT_PAGE_KEYS
from touchdeck.themes import build_qss, get_theme, Theme
from touchdeck.quick_actions import quick_action_lookup, QuickActionOption


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
        self.min_dy_px = 90
        self.max_dt_s = 0.85
        self.axis_bias = 1.35  # |dx| must be this much bigger than |dy|
        self.drawer_start_zone = 120

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
            if getattr(w, "objectName", lambda: "")() == "NotificationToast":
                return True
            if isinstance(w, QAbstractSlider):
                return True
            # also ignore if user starts on a button (tap should click)
            if w.metaObject().className() in ("QPushButton", "QToolButton"):
                if hasattr(self.host, "drawer") and getattr(self.host, "drawer").isAncestorOf(w):
                    return False
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

        # Allow easy downward swipe to close the drawer even with small movement.
        if dy > 30 and abs(dy) > abs(dx) and self.host.should_close_quick_actions():
            self.host.close_quick_actions()
            return

        # Vertical swipe: toggle quick actions drawer
        if abs(dy) >= self.min_dy_px and abs(dy) > abs(dx) * self.axis_bias:
            if dy < 0 and self.host.can_open_quick_actions(self.s.start_pos, self.drawer_start_zone):
                self.host.open_quick_actions()
                return
            if dy > 0 and self.host.should_close_quick_actions():
                self.host.close_quick_actions()
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
    def __init__(self, settings: Settings | None = None, logo_icon: QIcon | None = None) -> None:
        super().__init__()
        self.setObjectName("DeckWindow")
        self.setWindowTitle("touchdeck")
        self.setAttribute(Qt.WA_AcceptTouchEvents, True)
        self.setStyleSheet(f"border-radius: {CORNER_RADIUS}px;")

        self.settings = settings or load_settings()
        self._theme: Theme = get_theme(self.settings.theme)
        self._quick_action_options = quick_action_lookup()

        if self.settings.demo_mode:
            self._set_demo_window()
        else:
            self._clear_fixed_window()

        self._mpris = MprisService()
        self._stats = StatsService(enable_gpu=self.settings.enable_gpu_stats)
        self._speedtest = SpeedtestService()

        self.stack = QStackedWidget()
        self.page_music = MusicPage(self._theme)
        self.page_stats = StatsPage(self.settings, theme=self._theme)
        self.page_clock = ClockPage(self.settings, theme=self._theme)
        self.page_emoji = EmojiPage(theme=self._theme)
        self.page_speedtest = SpeedtestPage(self._on_speedtest_requested, theme=self._theme)
        self.page_settings = SettingsPage(
            self.settings,
            self._on_settings_changed,
            self._on_exit_requested,
            self._on_reset_requested,
            theme=self._theme,
        )

        self._pages = {
            "music": self.page_music,
            "stats": self.page_stats,
            "clock": self.page_clock,
            "emoji": self.page_emoji,
            "speedtest": self.page_speedtest,
            "settings": self.page_settings,
        }
        self._enabled_pages: list[str] = []
        self._rebuild_stack()

        self.dots = DotIndicator(self.stack.count(), theme=self._theme)
        self.dots.set_index(self.stack.currentIndex())

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 12)
        root.setSpacing(8)
        root.addWidget(self.stack, 1)
        root.addWidget(self.dots, 0)

        self.drawer = QuickActionsDrawer(self._on_quick_action_triggered, parent=self, theme=self._theme)
        self.drawer.update_actions(self._selected_quick_actions())
        self.drawer.set_bounds(self.width(), self.height())
        self.drawer.raise_()

        self.onboarding = OnboardingOverlay(
            parent=self,
            theme=self._theme,
            on_finished=self._on_onboarding_finished,
        )
        self.onboarding.set_bounds(self.width(), self.height())
        if not self.settings.onboarding_completed:
            self.onboarding.start()
        else:
            self.onboarding.hide()

        self.notification_stack = NotificationStack(parent=self, theme=self._theme)
        self.notification_stack.set_bounds(self.width(), self.height())
        self.notification_stack.raise_()

        self.startup = StartupOverlay(logo_icon, parent=self, theme=self._theme)
        self.startup.set_bounds(self.width(), self.height())
        self.startup.raise_()

        self._notification_listener = NotificationListener(self._on_system_notification)
        self._start_notification_listener()

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
        self.drawer.installEventFilter(self._swipe)

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
        self.startup.start()

    # Public for SwipeNavigator
    def next_page(self) -> None:
        idx = (self.stack.currentIndex() + 1) % self.stack.count()
        self._set_page(idx)

    def prev_page(self) -> None:
        idx = (self.stack.currentIndex() - 1) % self.stack.count()
        self._set_page(idx)

    def _set_page(self, idx: int) -> None:
        self.stack.setCurrentIndex(idx)
        if hasattr(self, "dots"):
            self.dots.set_index(idx)

    def resizeEvent(self, event) -> None:  # noqa: N802
        super().resizeEvent(event)
        self.drawer.set_bounds(self.width(), self.height())
        self.onboarding.set_bounds(self.width(), self.height())
        self.notification_stack.set_bounds(self.width(), self.height())
        self.startup.set_bounds(self.width(), self.height())

    def showEvent(self, event) -> None:  # noqa: N802
        super().showEvent(event)
        self._apply_display_preference()
        self._start_notification_listener()

    def _effective_enabled_pages(self) -> list[str]:
        pages = [p for p in self.settings.enabled_pages if p in self._pages]
        if "settings" not in pages:
            pages.append("settings")
        if not pages:
            pages = ["settings"]
        ordered = [p for p in DEFAULT_PAGE_KEYS if p in pages]
        for p in pages:
            if p not in ordered:
                ordered.append(p)
        return ordered

    def _current_page_key(self) -> str | None:
        current = self.stack.currentWidget()
        for key, widget in self._pages.items():
            if widget is current:
                return key
        return None

    def _rebuild_stack(self, keep_key: str | None = None) -> None:
        current_key = keep_key or self._current_page_key()
        for i in range(self.stack.count() - 1, -1, -1):
            widget = self.stack.widget(i)
            self.stack.removeWidget(widget)
        enabled = self._effective_enabled_pages()
        self._enabled_pages = enabled
        for key in enabled:
            self.stack.addWidget(self._pages[key])
        target_key = current_key if current_key in enabled else enabled[0]
        self._set_page(enabled.index(target_key))
        if hasattr(self, "dots"):
            self.dots.set_count(len(enabled))
            self.dots.set_index(self.stack.currentIndex())

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
        self._rebuild_stack(self._current_page_key())
        if self.settings.demo_mode:
            self._set_demo_window()
            self.showNormal()
        else:
            self._clear_fixed_window()
            self.showFullScreen()
        self._apply_display_preference()
        self.drawer.update_actions(self._selected_quick_actions())
        self.drawer.set_bounds(self.width(), self.height())
        if not self.drawer.has_actions():
            self.drawer.close_drawer()
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
        self.drawer.apply_theme(theme)
        self.onboarding.apply_theme(theme)
        self.notification_stack.apply_theme(theme)
        self.startup.apply_theme(theme)
        # Keep window border radius styling intact
        self.setStyleSheet(f"border-radius: {CORNER_RADIUS}px;")

    def _apply_display_preference(self) -> None:
        app = QApplication.instance()
        if app is None:
            return
        screens = app.screens()
        target = None
        if self.settings.preferred_display:
            for s in screens:
                if s.name() == self.settings.preferred_display:
                    target = s
                    break
        if target is None and screens:
            target = screens[0]
        handle = self.windowHandle()
        if handle is not None and target is not None:
            handle.setScreen(target)

    def _set_demo_window(self) -> None:
        self._clear_fixed_window()
        self.setFixedSize(WINDOW_W, WINDOW_H)

    def _clear_fixed_window(self) -> None:
        self.setMinimumSize(0, 0)
        self.setMaximumSize(16777215, 16777215)

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

    def _on_system_notification(self, notification: SystemNotification) -> None:
        duration = notification.expire_ms if notification.expire_ms and notification.expire_ms > 0 else None
        self.notification_stack.show_notification(notification.app_name, notification.summary, notification.body, duration_ms=duration)

    def _start_notification_listener(self) -> None:
        # Create task on the current loop when one exists and is running.
        try:
            loop = asyncio.get_event_loop()
        except RuntimeError:
            return
        try:
            loop.create_task(self._notification_listener.start())
        except RuntimeError:
            # Loop not running yet; we'll try again on showEvent.
            pass

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

    def _on_exit_requested(self) -> None:
        app = QApplication.instance()
        if app is not None:
            app.quit()

    def _on_reset_requested(self) -> None:
        # Clear persisted settings and restart the app fresh.
        reset_settings()
        app = QApplication.instance()
        if app is not None:
            QProcess.startDetached(sys.executable or "python", ["-m", "touchdeck"])
            app.quit()

    def _on_speedtest_requested(self) -> None:
        self.page_speedtest.set_running(True)
        asyncio.create_task(self._run_speedtest())

    async def _run_speedtest(self) -> None:
        try:
            result = await self._speedtest.run()
        except Exception as exc:
            self.page_speedtest.show_error(str(exc))
            return
        self.page_speedtest.show_result(result)

    def _selected_quick_actions(self) -> list[QuickActionOption]:
        return [self._quick_action_options[key] for key in self.settings.quick_actions if key in self._quick_action_options]

    def _on_quick_action_triggered(self, key: str) -> None:
        actions = {
            "play_pause": self._on_playpause,
            "next_track": self._on_next,
            "prev_track": self._on_prev,
            "run_speedtest": self._on_speedtest_requested,
            "toggle_gpu": self._toggle_gpu_stats_from_action,
        }
        action = actions.get(key)
        if action is not None:
            action()
        self.close_quick_actions()

    def _toggle_gpu_stats_from_action(self) -> None:
        new_settings = replace(self.settings, enable_gpu_stats=not self.settings.enable_gpu_stats)
        self._on_settings_changed(new_settings)

    def _on_onboarding_finished(self) -> None:
        if self.settings.onboarding_completed:
            return
        self.settings = replace(self.settings, onboarding_completed=True)
        save_settings(self.settings)

    def open_quick_actions(self) -> None:
        if self.drawer.has_actions():
            self.drawer.raise_()
            self.drawer.open_drawer()

    def close_quick_actions(self) -> None:
        if self.drawer.is_open():
            self.drawer.close_drawer()

    def can_open_quick_actions(self, start_pos: QPointF, start_zone_px: int) -> bool:
        if start_pos is None:
            return False
        if self.drawer.is_open() or not self.drawer.has_actions():
            return False
        return start_pos.y() >= (self.height() - start_zone_px)

    def should_close_quick_actions(self) -> bool:
        return self.drawer.is_open()
