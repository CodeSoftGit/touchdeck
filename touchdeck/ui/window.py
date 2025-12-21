from __future__ import annotations

import asyncio
import select
import subprocess
import threading
from dataclasses import dataclass, replace
import sys
from time import monotonic

from PySide6.QtCore import (
    Qt,
    QEvent,
    QTimer,
    QObject,
    QPointF,
    Slot,
    QProcess,
    QThread,
    Signal,
)
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import (
    QApplication,
    QWidget,
    QVBoxLayout,
    QStackedWidget,
    QAbstractSlider,
)

from touchdeck.constants import WINDOW_W, WINDOW_H, CORNER_RADIUS
from touchdeck.ui.pages import (
    MusicPage,
    StatsPage,
    ClockPage,
    SettingsPage,
    SpeedtestPage,
    EmojiPage,
)
from touchdeck.ui.widgets import (
    DotIndicator,
    QuickActionsDrawer,
    OnboardingOverlay,
    NotificationStack,
    StartupOverlay,
)
from touchdeck.services.mpris import MprisService
from touchdeck.services.stats import StatsService
from touchdeck.services.speedtest import SpeedtestService
from touchdeck.services.notifications import NotificationListener, SystemNotification
from touchdeck.LRCLIB import LrclibClient, LyricLine, SyncedLyrics, LyricsNotFoundError
from touchdeck.settings import (
    load_settings,
    save_settings,
    reset_settings,
    Settings,
    DEFAULT_PAGE_KEYS,
)
from touchdeck.themes import build_qss, get_theme, Theme
from touchdeck.quick_actions import (
    CustomQuickAction,
    quick_action_lookup,
    QuickActionOption,
)
from touchdeck.utils import ms_to_mmss


@dataclass
class _SwipeState:
    active: bool = False
    ignore: bool = False
    start_pos: QPointF | None = None
    start_t: float = 0.0


class _CommandWorker(QObject):
    output = Signal(str)
    finished = Signal(int, bool, bool)
    error = Signal(str)

    def __init__(
        self, command: str, timeout_ms: int, cancel_event: threading.Event
    ) -> None:
        super().__init__()
        self._command = command
        self._timeout_ms = timeout_ms
        self._cancel_event = cancel_event

    @Slot()
    def run(self) -> None:
        start = monotonic()
        timed_out = False
        canceled = False
        try:
            proc = subprocess.Popen(
                self._command,
                shell=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,
            )
        except Exception as exc:
            self.error.emit(str(exc))
            self.finished.emit(1, False, False)
            return

        try:
            stdout = proc.stdout
            fd = stdout.fileno() if stdout else None
            while True:
                if self._cancel_event.is_set():
                    canceled = True
                    proc.terminate()
                if self._timeout_ms > 0:
                    elapsed_ms = int((monotonic() - start) * 1000)
                    if elapsed_ms > self._timeout_ms:
                        timed_out = True
                        proc.terminate()

                if fd is not None:
                    ready, _, _ = select.select([fd], [], [], 0.2)
                    if ready:
                        line = stdout.readline()
                        if line:
                            self.output.emit(line.rstrip("\n"))
                            continue

                if proc.poll() is not None:
                    break

                if canceled or timed_out:
                    try:
                        proc.wait(timeout=1)
                    except Exception:
                        proc.kill()
                        proc.wait()
                    break

            if stdout is not None:
                for line in stdout:
                    if line:
                        self.output.emit(line.rstrip("\n"))
        except Exception as exc:
            self.error.emit(str(exc))
        finally:
            exit_code = proc.poll()
            if exit_code is None:
                try:
                    exit_code = proc.wait(timeout=1)
                except Exception:
                    exit_code = 1
            self.finished.emit(int(exit_code or 0), timed_out, canceled)


@dataclass
class _RunningCommand:
    thread: QThread
    worker: _CommandWorker
    action: CustomQuickAction
    cancel_event: threading.Event
    last_line: str = ""


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
                if hasattr(self.host, "drawer") and getattr(
                    self.host, "drawer"
                ).isAncestorOf(w):
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
            if dy < 0 and self.host.can_open_quick_actions(
                self.s.start_pos, self.drawer_start_zone
            ):
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
    def __init__(
        self,
        settings: Settings | None = None,
        logo_icon: QIcon | None = None,
        startup_logo_icon: QIcon | None = None,
    ) -> None:
        super().__init__()
        self.setObjectName("DeckWindow")
        self.setWindowTitle("touchdeck")
        self.setAttribute(Qt.WA_AcceptTouchEvents, True)
        self.setStyleSheet(f"border-radius: {CORNER_RADIUS}px;")

        self.settings = settings or load_settings()
        self._theme: Theme = get_theme(self.settings.theme)
        self._quick_action_options = quick_action_lookup(self.settings.custom_actions)
        self._custom_actions = {a.key: a for a in self.settings.custom_actions}
        self._running_custom_actions: dict[str, _RunningCommand] = {}

        if self.settings.demo_mode:
            self._set_demo_window()
        else:
            self._clear_fixed_window()

        self._mpris = MprisService()
        self._lyrics_client = LrclibClient()
        self._lyrics_task: asyncio.Task | None = None
        self._lyrics_track_key: str | None = None
        self._lyrics: SyncedLyrics | None = None
        self._stats = StatsService(enable_gpu=self.settings.enable_gpu_stats)
        self._speedtest = SpeedtestService()

        self.stack = QStackedWidget()
        self.page_music = MusicPage(self._theme)
        self.page_stats = StatsPage(self.settings, theme=self._theme)
        self.page_clock = ClockPage(self.settings, theme=self._theme)
        self.page_emoji = EmojiPage(theme=self._theme)
        self.page_speedtest = SpeedtestPage(
            self._on_speedtest_requested, theme=self._theme
        )
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

        self.drawer = QuickActionsDrawer(
            self._on_quick_action_triggered,
            parent=self,
            theme=self._theme,
            on_cancel=self._on_quick_action_canceled,
        )
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

        self.startup = StartupOverlay(
            startup_logo_icon or logo_icon, parent=self, theme=self._theme
        )
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
        self._custom_actions = {a.key: a for a in self.settings.custom_actions}
        self._quick_action_options = quick_action_lookup(self.settings.custom_actions)
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
        self._maybe_update_lyrics(np)
        self.page_music.set_now_playing(np)

    def _maybe_update_lyrics(self, np: NowPlaying) -> None:
        key = self._lyrics_key(np)
        if key == self._lyrics_track_key:
            return
        self._lyrics_track_key = key
        self._lyrics = None
        self.page_music.set_synced_lyrics(None)
        self._cancel_lyrics_task()
        if key is None:
            return
        cached = self._cached_lyrics_for_track(key)
        if cached is not None:
            self._lyrics = cached
            self.page_music.set_synced_lyrics(cached)
            return
        self._lyrics_task = asyncio.create_task(self._fetch_lyrics(np, key))

    def _cached_lyrics_for_track(self, track_key: str | None) -> SyncedLyrics | None:
        if track_key is None:
            return None
        entries = self.settings.lyrics_cache.get(track_key)
        if not isinstance(entries, list):
            return None
        lines: list[LyricLine] = []
        for entry in entries:
            if not isinstance(entry, dict):
                continue
            at_ms = entry.get("at_ms")
            text = entry.get("text")
            if not isinstance(at_ms, int) or at_ms < 0:
                continue
            if not isinstance(text, str):
                continue
            lines.append(LyricLine(at_ms=at_ms, text=text))
        if not lines:
            return None
        lines.sort(key=lambda line: line.at_ms)
        return SyncedLyrics(lines=lines)

    def _lyrics_key(self, np: NowPlaying) -> str | None:
        if not np.title or not np.artist:
            return None
        if not np.length_ms or np.length_ms <= 0:
            return None
        duration_s = int(round(np.length_ms / 1000))
        album = np.album.strip() if np.album else ""
        return f"{np.track_id or ''}|{np.title.strip()}|{np.artist.strip()}|{album}|{duration_s}"

    def _cancel_lyrics_task(self) -> None:
        if self._lyrics_task is None:
            return
        self._lyrics_task.cancel()
        self._lyrics_task = None

    async def _fetch_lyrics(self, np: NowPlaying, track_key: str) -> None:
        not_found = False
        try:
            lyrics = await self._lyrics_client.fetch_synced(
                track_name=np.title,
                artist_name=np.artist,
                album_name=np.album or "",
                duration_ms=int(np.length_ms or 0),
            )
        except asyncio.CancelledError:
            return
        except LyricsNotFoundError:
            lyrics = None
            not_found = True
        except Exception:
            lyrics = None
        finally:
            if asyncio.current_task() is self._lyrics_task:
                self._lyrics_task = None

        if track_key != self._lyrics_track_key:
            return
        self._lyrics = lyrics
        if lyrics is not None:
            self._cache_lyrics(track_key, lyrics)
        if not_found:
            self.page_music.show_lyrics_message("Could not find lyrics", 10_000)
        self.page_music.set_synced_lyrics(lyrics)

    def _cache_lyrics(self, track_key: str, lyrics: SyncedLyrics) -> None:
        lines = [
            {"at_ms": line.at_ms, "text": line.text}
            for line in lyrics.lines
            if isinstance(line.text, str)
        ]
        if not lines:
            return
        self.settings.lyrics_cache[track_key] = lines
        save_settings(self.settings)

    @Slot()
    def _poll_stats(self) -> None:
        s = self._stats.read()
        self.page_stats.set_stats(s)

    def _on_system_notification(self, notification: SystemNotification) -> None:
        duration = (
            notification.expire_ms
            if notification.expire_ms and notification.expire_ms > 0
            else None
        )
        self.notification_stack.show_notification(
            notification.app_name,
            notification.summary,
            notification.body,
            duration_ms=duration,
        )

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
        return [
            self._quick_action_options[key]
            for key in self.settings.quick_actions
            if key in self._quick_action_options
        ]

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
        elif key in self._custom_actions:
            asyncio.create_task(self._run_custom_action(self._custom_actions[key]))
        self.close_quick_actions()

    def _on_quick_action_canceled(self, key: str) -> None:
        if key in self._custom_actions:
            self._cancel_custom_action(key)

    def _toggle_gpu_stats_from_action(self) -> None:
        new_settings = replace(
            self.settings, enable_gpu_stats=not self.settings.enable_gpu_stats
        )
        self._on_settings_changed(new_settings)

    async def _run_custom_action(self, action: CustomQuickAction) -> None:
        if action.key in self._running_custom_actions:
            return
        now_playing = await self._mpris.now_playing()
        command = self._format_custom_command(action.command, now_playing)
        cancel_event = threading.Event()
        worker = _CommandWorker(command, action.timeout_ms, cancel_event)
        thread = QThread(self)
        worker.moveToThread(thread)
        worker.output.connect(
            lambda line, key=action.key: self._on_action_output(key, line)
        )
        worker.error.connect(
            lambda msg, key=action.key: self._on_action_error(key, msg)
        )
        worker.finished.connect(
            lambda code, timed_out, canceled, key=action.key: self._on_action_finished(
                key, code, timed_out, canceled
            )
        )
        worker.finished.connect(thread.quit)
        worker.finished.connect(worker.deleteLater)
        thread.finished.connect(thread.deleteLater)
        self._running_custom_actions[action.key] = _RunningCommand(
            thread=thread,
            worker=worker,
            action=action,
            cancel_event=cancel_event,
            last_line="",
        )
        self.drawer.update_action_detail(action.key, "Running...")
        thread.start()

    def _cancel_custom_action(self, key: str) -> None:
        running = self._running_custom_actions.get(key)
        if running is None:
            return
        running.cancel_event.set()
        self.drawer.update_action_detail(key, "Canceling...")

    def _on_action_output(self, key: str, line: str) -> None:
        running = self._running_custom_actions.get(key)
        if running is None:
            return
        clean = " ".join((line or "").splitlines()).strip()
        if not clean:
            return
        running.last_line = clean
        self.drawer.update_action_detail(key, clean)

    def _on_action_error(self, key: str, msg: str) -> None:
        running = self._running_custom_actions.get(key)
        if running is None:
            return
        clean = " ".join((msg or "").splitlines()).strip()
        if clean:
            running.last_line = clean
            self.drawer.update_action_detail(key, clean)

    def _on_action_finished(
        self, key: str, exit_code: int, timed_out: bool, canceled: bool
    ) -> None:
        running = self._running_custom_actions.pop(key, None)
        if running is None:
            return
        title = running.action.title
        detail = running.last_line
        if timed_out:
            self.drawer.update_action_detail(key, "Timed out")
            self._show_quick_action_toast(f"{title} timed out", detail)
            return
        if canceled:
            self.drawer.update_action_detail(key, "Canceled")
            self._show_quick_action_toast(f"{title} canceled", detail)
            return
        if exit_code == 0:
            self._show_quick_action_toast(f"{title} succeeded", detail)
        else:
            self._show_quick_action_toast(f"{title} failed", detail)

    def _show_quick_action_toast(self, summary: str, body: str) -> None:
        self.notification_stack.show_notification(
            "Quick actions", summary, body or "", duration_ms=3500
        )

    def _format_custom_command(self, template: str, now_playing) -> str:
        ctx = {
            "title": now_playing.title or "",
            "artist": now_playing.artist or "",
            "album": now_playing.album or "",
            "status": now_playing.status or "",
            "position_ms": str(now_playing.position_ms or 0),
            "length_ms": str(now_playing.length_ms or 0),
            "position_mmss": ms_to_mmss(int(now_playing.position_ms or 0)),
            "length_mmss": ms_to_mmss(int(now_playing.length_ms or 0)),
            "track_id": now_playing.track_id or "",
            "bus_name": now_playing.bus_name or "",
        }

        class _SafeDict(dict):
            def __missing__(self, key: str) -> str:
                return ""

        try:
            return template.format_map(_SafeDict(ctx))
        except Exception:
            return template

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
