from __future__ import annotations

import math
from typing import Callable

from PySide6.QtCore import Qt, QSize, QRectF, QVariantAnimation, QAbstractAnimation, QPropertyAnimation, QEvent, QPoint, QPointF, QTimer
from PySide6.QtGui import QColor, QPainter, QPainterPath, QPen, QFontMetrics, QLinearGradient, QRadialGradient, QIcon, QPixmap
from PySide6.QtWidgets import (
    QWidget,
    QPushButton,
    QLabel,
    QHBoxLayout,
    QVBoxLayout,
    QProgressBar,
    QGraphicsDropShadowEffect,
    QGridLayout,
)

from touchdeck.animations import easing_curve
from touchdeck.themes import Theme, get_theme
from touchdeck.quick_actions import QuickActionOption


class Card(QWidget):
    def __init__(self, radius: int = 22, parent: QWidget | None = None, theme: Theme | None = None) -> None:
        super().__init__(parent)
        self._radius = radius
        self._theme = theme or get_theme(None)
        self.setAttribute(Qt.WA_StyledBackground, True)
        self._apply_theme()

        # Subtle depth without looking like 2012 skeuomorphism
        shadow = QGraphicsDropShadowEffect(self)
        shadow.setBlurRadius(22)
        shadow.setOffset(0, 10)
        shadow.setColor(QColor(0, 0, 0, 160))
        self.setGraphicsEffect(shadow)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(24, 22, 24, 20)
        lay.setSpacing(14)
        self._layout = lay

    @property
    def body(self) -> QVBoxLayout:
        return self._layout

    def apply_theme(self, theme: Theme) -> None:
        self._theme = theme
        self._apply_theme()

    def _apply_theme(self) -> None:
        self.setStyleSheet(
            f"background: {self._theme.panel}; border-radius: {self._radius}px;"
        )


class ElideLabel(QLabel):
    """QLabel that always elides text to fit its width.

    Uses QFontMetrics.elidedText(...), which is pixel-based and reliable.
    """

    def __init__(self, text: str = "", *, mode: Qt.TextElideMode = Qt.ElideRight, parent: QWidget | None = None) -> None:
        super().__init__("", parent)
        self._full = text or ""
        self._mode = mode
        self.setText(text)

    def setText(self, text: str) -> None:  # type: ignore[override]
        self._full = text or ""
        self._update_elide()

    def fullText(self) -> str:
        return self._full

    def resizeEvent(self, ev) -> None:
        super().resizeEvent(ev)
        self._update_elide()

    def _update_elide(self) -> None:
        fm = QFontMetrics(self.font())
        w = max(0, self.width() - 2)
        elided = fm.elidedText(self._full, self._mode, w)
        super().setText(elided)


class DotIndicator(QWidget):
    def __init__(self, count: int, parent: QWidget | None = None, theme: Theme | None = None) -> None:
        super().__init__(parent)
        self._count = count
        self._index = 0
        self._theme = theme or get_theme(None)
        self._anim_value = float(self._index)
        self._anim = QVariantAnimation(self)
        self._anim.setDuration(200)
        self._anim.setEasingCurve(easing_curve())
        self._anim.valueChanged.connect(self._on_anim_value)
        self.setFixedHeight(18)

    def set_index(self, idx: int) -> None:
        idx = max(0, min(self._count - 1, idx))
        if idx != self._index:
            start = self._anim_value if self._anim.state() == QAbstractAnimation.Running else float(self._index)
            self._index = idx
            self._anim.stop()
            self._anim.setStartValue(start)
            self._anim.setEndValue(float(idx))
            self._anim.start()

    def apply_theme(self, theme: Theme) -> None:
        self._theme = theme
        self.update()

    def set_count(self, count: int) -> None:
        count = max(1, int(count))
        self._count = count
        self._index = min(self._index, self._count - 1)
        self._anim.stop()
        self._anim_value = float(self._index)
        self.update()

    def _on_anim_value(self, value) -> None:
        self._anim_value = float(value)
        self.update()

    def paintEvent(self, _ev) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing, True)

        dot_r = 3.0
        dot_gap = 12
        active_r = 4.6

        width = (self._count - 1) * dot_gap + active_r * 2
        x0 = (self.width() - width) / 2.0
        y = self.height() / 2.0

        for i in range(self._count):
            r = dot_r
            p.setBrush(QColor(self._theme.subtle))
            p.setPen(Qt.NoPen)
            cx = x0 + i * dot_gap
            p.drawEllipse(QRectF(cx - r, y - r, 2 * r, 2 * r))

        # Active indicator slides with easing between dots
        active_cx = x0 + self._anim_value * dot_gap
        p.setBrush(QColor(self._theme.accent))
        p.setPen(Qt.NoPen)
        p.drawEllipse(QRectF(active_cx - active_r, y - active_r, 2 * active_r, 2 * active_r))


class StartupOverlay(QWidget):
    """Short intro flash that fades the logo in/out on startup."""

    def __init__(self, logo_icon: QIcon | None, *, parent: QWidget | None = None, theme: Theme | None = None) -> None:
        super().__init__(parent)
        self._theme = theme or get_theme(None)
        self._logo_icon = logo_icon or QIcon()
        self._logo_pixmap: QPixmap | None = None
        self._opacity = 0.0
        self._scale = 0.9
        self._glow_strength = 0.0
        self._ring_strength = 0.0
        self._parallax = 0.0
        self._sweep_progress = 0.0
        self._echo_strength = 0.0

        self.setAttribute(Qt.WA_StyledBackground, True)
        self.setVisible(False)

        self._timeline = QVariantAnimation(self)
        self._timeline.setEasingCurve(easing_curve())
        self._timeline.setDuration(2400)
        self._timeline.setStartValue(0.0)
        self._timeline.setEndValue(1.0)
        self._timeline.valueChanged.connect(self._on_timeline_value)
        self._timeline.finished.connect(self._on_anim_finished)

        self.apply_theme(self._theme)
        self._apply_logo_pixmap()

    def set_bounds(self, width: int, height: int) -> None:
        self.setGeometry(0, 0, width, height)
        self._apply_logo_pixmap()

    def apply_theme(self, theme: Theme) -> None:
        self._theme = theme
        self.update()

    def start(self) -> None:
        if self._logo_icon.isNull():
            return
        self._set_opacity(0.0)
        self._scale = 0.9
        self._glow_strength = 0.0
        self._ring_strength = 0.0
        self._parallax = 0.0
        self._sweep_progress = 0.0
        self._echo_strength = 0.0
        self._timeline.stop()
        self._timeline.setCurrentTime(0)
        self.show()
        self.raise_()
        self._timeline.start()

    def _on_timeline_value(self, value) -> None:
        progress = max(0.0, min(1.0, float(value)))
        clamp = lambda v, lo=0.0, hi=1.0: max(lo, min(hi, v))

        fade_in = clamp(progress / 0.22)
        drift = clamp((progress - 0.1) / 0.7)
        linger = clamp((progress - 0.6) / 0.28)
        fade_out = clamp((progress - 0.78) / 0.22)

        pulse = math.sin(clamp((progress - 0.12) / 0.6) * math.pi)
        hover = math.sin(clamp((progress - 0.02) / 0.7) * math.pi * 0.75)

        self._parallax = (math.sin(progress * math.pi) * 0.5 + 0.5) * 18.0
        self._sweep_progress = drift
        self._echo_strength = (pulse ** 1.25) if pulse > 0.0 else 0.0

        self._set_opacity(fade_in * (1.0 - fade_out * 0.9))
        self._scale = 0.9 + 0.16 * fade_in + 0.08 * hover - 0.05 * fade_out
        self._glow_strength = clamp(0.25 + 0.55 * fade_in + 0.25 * pulse - 0.45 * fade_out, 0.0, 1.2)
        self._ring_strength = clamp(0.1 + 0.65 * pulse + 0.35 * linger, 0.0, 1.0)
        self.update()

    def _on_anim_finished(self) -> None:
        self.hide()

    def _apply_logo_pixmap(self) -> None:
        if self._logo_icon.isNull():
            self._logo_pixmap = None
            return
        side = int(max(200, min(420, min(self.width(), self.height()) * 0.5))) or 240
        self._logo_pixmap = self._logo_icon.pixmap(side, side)

    def _set_opacity(self, value: float) -> None:
        self._opacity = max(0.0, min(1.0, value))
        self.update()

    def paintEvent(self, ev) -> None:
        super().paintEvent(ev)
        if self._opacity <= 0.0 or self._logo_pixmap is None:
            return
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, True)
        grad = QLinearGradient(0, -self._parallax, 0, self.height() + self._parallax)
        top = QColor(self._theme.gradient_top)
        bottom = QColor(self._theme.gradient_bottom)
        top.setAlphaF(self._opacity)
        bottom.setAlphaF(self._opacity)
        grad.setColorAt(0, top)
        grad.setColorAt(1, bottom)
        painter.fillRect(self.rect(), grad)

        if self._sweep_progress > 0.0:
            band_width = self.width() * 0.38
            sweep_x = (self._sweep_progress * 1.4 - 0.2) * self.width()
            beam = QLinearGradient(sweep_x - band_width, 0, sweep_x + band_width, self.height())
            accent = QColor(self._theme.accent).lighter(135)
            accent_mid = QColor(accent)
            accent_mid.setAlphaF(0.7 * self._opacity * accent_mid.alphaF())
            accent.setAlphaF(0.14 * self._opacity)
            transparent = QColor(accent)
            transparent.setAlpha(0)
            beam.setColorAt(0.0, transparent)
            beam.setColorAt(0.42, accent_mid)
            beam.setColorAt(0.5, accent)
            beam.setColorAt(1.0, transparent)
            painter.fillRect(self.rect(), beam)

        target_w = int(self._logo_pixmap.width() * self._scale)
        target_h = int(self._logo_pixmap.height() * self._scale)
        target_w = max(1, target_w)
        target_h = max(1, target_h)
        scaled = self._logo_pixmap.scaled(target_w, target_h, Qt.KeepAspectRatio, Qt.SmoothTransformation)
        cx = self.width() / 2
        cy = self.height() / 2
        ring_radius_base = max(scaled.width(), scaled.height()) / 2 + 24

        if self._glow_strength > 0.0:
            halo_radius = max(scaled.width(), scaled.height()) * 0.9 + 90
            accent = QColor(self._theme.accent)
            accent.setAlphaF(0.22 * self._glow_strength)
            halo_mid = QColor(self._theme.accent)
            halo_mid.setAlphaF(0.08 * self._glow_strength)
            halo = QRadialGradient(QPointF(cx, cy), halo_radius)
            halo.setColorAt(0.0, accent)
            halo.setColorAt(0.55, halo_mid)
            halo.setColorAt(1.0, QColor(accent.red(), accent.green(), accent.blue(), 0))
            painter.fillRect(self.rect(), halo)

        painter.save()
        painter.setOpacity(self._opacity)
        x = (self.width() - scaled.width()) // 2
        y = (self.height() - scaled.height()) // 2
        painter.drawPixmap(x, y, scaled)
        painter.restore()

        if self._ring_strength > 0.0:
            ring_color = QColor(self._theme.accent)
            ring_color.setAlphaF(0.35 * self._ring_strength)
            pen = QPen(ring_color)
            pen.setWidth(3)
            pen.setCapStyle(Qt.RoundCap)
            painter.setPen(pen)
            painter.setBrush(Qt.NoBrush)
            ring_radius = ring_radius_base + 90 * self._ring_strength
            painter.drawEllipse(QPointF(cx, cy), ring_radius, ring_radius)

        if self._echo_strength > 0.0:
            echo_color = QColor(self._theme.accent)
            echo_color.setAlphaF(0.16 * self._echo_strength * self._opacity)
            pen = QPen(echo_color)
            pen.setWidth(6)
            pen.setCapStyle(Qt.RoundCap)
            painter.setPen(pen)
            painter.setBrush(Qt.NoBrush)
            echo_radius = ring_radius_base + 110 + 120 * self._echo_strength
            painter.drawEllipse(QPointF(cx, cy), echo_radius, echo_radius)


class IconButton(QPushButton):
    """A rounded button with a simple drawn icon."""

    def __init__(
        self,
        kind: str,
        *,
        diameter: int = 54,
        filled: bool = False,
        parent: QWidget | None = None,
        theme: Theme | None = None,
    ) -> None:
        super().__init__(parent)
        self.kind = kind
        self.diameter = diameter
        self.filled = filled
        self._theme = theme or get_theme(None)
        self.setCursor(Qt.PointingHandCursor)
        self.setFixedSize(diameter, diameter)
        self.setFlat(True)

    def sizeHint(self) -> QSize:
        return QSize(self.diameter, self.diameter)

    def set_theme(self, theme: Theme) -> None:
        self._theme = theme
        self.update()

    def paintEvent(self, _ev) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing, True)

        rect = QRectF(0, 0, self.width(), self.height())
        r = rect.width() / 2.0

        down = self.isDown()
        hover = self.underMouse()

        # background
        if self.filled:
            bg = QColor(self._theme.accent)
            if down:
                bg = QColor(self._theme.accent_pressed)
            p.setBrush(bg)
            p.setPen(Qt.NoPen)
            p.drawEllipse(rect)
            icon_color = QColor(self._theme.background)
        else:
            bg = QColor(self._theme.neutral)
            if hover:
                bg = QColor(self._theme.neutral_hover)
            if down:
                bg = QColor(self._theme.neutral_pressed)
            p.setBrush(bg)
            p.setPen(Qt.NoPen)
            p.drawEllipse(rect)
            icon_color = QColor(self._theme.text)

        # icon
        p.setPen(Qt.NoPen)
        p.setBrush(icon_color)

        def triangle(center_x: float, center_y: float, w: float, h: float, direction: int) -> QPainterPath:
            # direction: +1 = right, -1 = left
            path = QPainterPath()
            if direction > 0:
                path.moveTo(center_x - w / 2, center_y - h / 2)
                path.lineTo(center_x - w / 2, center_y + h / 2)
                path.lineTo(center_x + w / 2, center_y)
            else:
                path.moveTo(center_x + w / 2, center_y - h / 2)
                path.lineTo(center_x + w / 2, center_y + h / 2)
                path.lineTo(center_x - w / 2, center_y)
            path.closeSubpath()
            return path

        cx, cy = rect.center().x(), rect.center().y()
        if self.kind == "play":
            path = triangle(cx + 2, cy, r * 0.75, r * 0.9, +1)
            p.drawPath(path)
        elif self.kind == "pause":
            w = r * 0.22
            h = r * 0.9
            gap = r * 0.14
            p.drawRoundedRect(QRectF(cx - gap - w, cy - h / 2, w, h), 2, 2)
            p.drawRoundedRect(QRectF(cx + gap, cy - h / 2, w, h), 2, 2)
        elif self.kind == "prev":
            bar_w = r * 0.12
            h = r * 0.9
            p.drawRoundedRect(QRectF(cx - r * 0.55, cy - h / 2, bar_w, h), 2, 2)
            path = triangle(cx + r * 0.05, cy, r * 0.70, r * 0.9, -1)
            p.drawPath(path)
        elif self.kind == "next":
            bar_w = r * 0.12
            h = r * 0.9
            p.drawRoundedRect(QRectF(cx + r * 0.43, cy - h / 2, bar_w, h), 2, 2)
            path = triangle(cx - r * 0.05, cy, r * 0.70, r * 0.9, +1)
            p.drawPath(path)
        else:
            p.drawEllipse(QRectF(cx - 4, cy - 4, 8, 8))


class QuickActionsDrawer(QWidget):
    """Bottom drawer that reveals quick actions via swipe or tap."""

    def __init__(
        self,
        on_trigger,
        *,
        parent: QWidget | None = None,
        theme: Theme | None = None,
        drawer_height: int = 220,
        peek_height: int = 16,
    ) -> None:
        super().__init__(parent)
        self._on_trigger = on_trigger
        self._theme = theme or get_theme(None)
        self._drawer_height = drawer_height
        self._peek_height = peek_height
        self._is_open = False
        self._actions: list[QuickActionOption] = []
        self._buttons: list[QPushButton] = []

        self.setAttribute(Qt.WA_StyledBackground, True)
        self.setFixedHeight(self._drawer_height)

        self._anim = QPropertyAnimation(self, b"pos")
        self._anim.setDuration(240)
        self._anim.setEasingCurve(easing_curve())

        self._grabber = QWidget()
        self._grabber.setFixedSize(48, 6)

        self._title = QLabel("Quick actions")
        self._title.setStyleSheet("font-size: 18px; font-weight: 700;")

        self._actions_layout = QGridLayout()
        self._actions_layout.setContentsMargins(0, 0, 0, 0)
        self._actions_layout.setSpacing(10)

        container = QWidget()
        container_layout = QVBoxLayout(container)
        container_layout.setContentsMargins(18, 12, 18, 16)
        container_layout.setSpacing(10)
        container_layout.addWidget(self._grabber, alignment=Qt.AlignCenter)
        container_layout.addWidget(self._title)
        container_layout.addLayout(self._actions_layout)
        container_layout.addStretch(1)

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)
        root.addWidget(container)

        self._apply_theme()
        self.show()

    def is_open(self) -> bool:
        return self._is_open

    def has_actions(self) -> bool:
        return bool(self._actions)

    def set_bounds(self, width: int, parent_height: int, *, animate: bool = False) -> None:
        self.setFixedWidth(width)
        target_y = self._open_y(parent_height) if self._is_open else self._closed_y(parent_height)
        if animate:
            self._animate_to(target_y)
        else:
            self.move(0, target_y)

    def update_actions(self, actions: list[QuickActionOption]) -> None:
        # Clear current buttons
        while self._actions_layout.count():
            item = self._actions_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()
        self._buttons.clear()
        self._actions = list(actions)

        if not actions:
            self._is_open = False
            self.hide()
            return

        self.show()
        for idx, action in enumerate(actions):
            btn = QPushButton(f"{action.label}\n{action.description}")
            btn.setCursor(Qt.PointingHandCursor)
            btn.setMinimumHeight(68)
            btn.clicked.connect(lambda _=False, key=action.key: self._trigger(key))
            self._style_button(btn)
            row, col = divmod(idx, 2)
            self._actions_layout.addWidget(btn, row, col)
            self._buttons.append(btn)

    def apply_theme(self, theme: Theme) -> None:
        self._theme = theme
        self._apply_theme()
        for btn in self._buttons:
            self._style_button(btn)

    def open_drawer(self) -> None:
        if self._is_open or not self.has_actions():
            return
        self._is_open = True
        parent_h = self.parent().height() if self.parent() else self.height()
        self._animate_to(self._open_y(parent_h))

    def close_drawer(self) -> None:
        if not self._is_open:
            return
        self._is_open = False
        parent_h = self.parent().height() if self.parent() else self.height()
        self._animate_to(self._closed_y(parent_h))

    def toggle(self) -> None:
        if self._is_open:
            self.close_drawer()
        elif self.has_actions():
            self.open_drawer()

    def mousePressEvent(self, _ev) -> None:  # noqa: N802
        if not self._is_open and self.has_actions():
            self.open_drawer()
        super().mousePressEvent(_ev)

    def _trigger(self, key: str) -> None:
        if callable(self._on_trigger):
            self._on_trigger(key)

    def _open_y(self, parent_height: int) -> int:
        return max(0, parent_height - self._drawer_height)

    def _closed_y(self, parent_height: int) -> int:
        # Leave a small grabber visible so the drawer is discoverable.
        return max(0, parent_height - self._peek_height)

    def _animate_to(self, y: int) -> None:
        self._anim.stop()
        start = self.pos()
        self._anim.setStartValue(start)
        self._anim.setEndValue(start.__class__(start.x(), y))
        self._anim.start()

    def _apply_theme(self) -> None:
        self.setStyleSheet(
            f"""
            QWidget {{
                background: {self._theme.panel};
                border-top-left-radius: 18px;
                border-top-right-radius: 18px;
            }}
            """
        )
        self._grabber.setStyleSheet(
            f"background: {self._theme.subtle}; border-radius: 3px;"
        )

    def _style_button(self, btn: QPushButton) -> None:
        btn.setStyleSheet(
            f"""
            QPushButton {{
                text-align: left;
                padding: 12px 14px;
                font-size: 18px;
                font-weight: 650;
                border-radius: 14px;
                background: {self._theme.neutral};
                color: {self._theme.text};
            }}
            QPushButton:pressed {{
                background: {self._theme.neutral_pressed};
            }}
            """
        )


class NotificationToast(QWidget):
    """Bottom toast used for system notifications with swipe-to-dismiss."""

    def __init__(
        self,
        *,
        parent: QWidget | None = None,
        theme: Theme | None = None,
        bottom_margin: int = 18,
        side_margin: int = 18,
        on_closed=None,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("NotificationToast")
        self.setAttribute(Qt.WA_StyledBackground, True)
        self.setAttribute(Qt.WA_AcceptTouchEvents, True)
        self._theme = theme or get_theme(None)
        self._bottom_margin = bottom_margin
        self._side_margin = side_margin
        self._parent_width = 0
        self._parent_height = 0
        self._target_pos = QPoint(0, 0)
        self._anim_mode = "idle"
        self._drag_start: QPointF | None = None
        self._dragging = False
        self._remaining_ms = 0
        self._on_closed = on_closed

        lay = QVBoxLayout(self)
        lay.setContentsMargins(18, 14, 18, 14)
        lay.setSpacing(4)

        self._title = ElideLabel("")
        self._title.setObjectName("NotificationTitle")
        self._body = ElideLabel("")
        self._body.setObjectName("NotificationBody")
        self._body.setVisible(False)

        lay.addWidget(self._title)
        lay.addWidget(self._body)

        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.timeout.connect(self.hide_toast)

        self._anim = QPropertyAnimation(self, b"pos")
        self._anim.setDuration(220)
        self._anim.setEasingCurve(easing_curve())
        self._anim.finished.connect(self._on_anim_finished)

        self.apply_theme(self._theme)
        self.hide()

    def apply_theme(self, theme: Theme) -> None:
        self._theme = theme
        self.setStyleSheet(
            f"""
            QWidget#NotificationToast {{
                background: rgba(0, 0, 0, 210);
                border: 1px solid {theme.subtle};
                border-radius: 16px;
            }}
            QLabel#NotificationTitle {{
                color: {theme.text};
                font-size: 18px;
                font-weight: 800;
            }}
            QLabel#NotificationBody {{
                color: {theme.subtle};
                font-size: 15px;
                font-weight: 650;
            }}
            """
        )

    def set_bounds(self, width: int, height: int) -> None:
        self._parent_width = width
        self._parent_height = height
        self._recompute_target()
        self._retarget()

    def set_bottom_margin(self, margin: int) -> None:
        self._bottom_margin = margin
        self._recompute_target()
        self._retarget()

    def set_on_closed(self, cb) -> None:
        self._on_closed = cb

    def show_notification(self, app_name: str, summary: str, body: str, duration_ms: int | None = None) -> None:
        clean_summary = " ".join((summary or "").splitlines()).strip()
        clean_body = " ".join((body or "").splitlines()).strip()
        title_parts = [p for p in (app_name, clean_summary) if p]
        title = " — ".join(title_parts) if title_parts else "Notification"
        self._title.setText(title)
        self._body.setText(clean_body)
        self._body.setVisible(bool(clean_body))
        self._remaining_ms = max(duration_ms or 4500, 1500)

        self._recompute_target()
        if self._parent_height <= 0:
            return

        start = QPoint(self._target_pos.x(), self._parent_height + self.height())
        self._timer.stop()
        self.move(start)
        self.show()
        self.raise_()
        self._animate_to(self._target_pos, mode="show")
        self._timer.start(self._remaining_ms)

    def hide_toast(self) -> None:
        if not self.isVisible():
            return
        self._timer.stop()
        end = QPoint(self._target_pos.x(), self._parent_height + self.height() + 12)
        self._animate_to(end, mode="hide")

    def event(self, ev) -> bool:  # noqa: N802
        t = ev.type()
        if t == QEvent.TouchBegin:
            pts = ev.points()
            if pts:
                self._begin_drag(pts[0].position())
            return True
        if t == QEvent.TouchUpdate:
            pts = ev.points()
            if pts:
                self._update_drag(pts[0].position())
            return True
        if t in (QEvent.TouchEnd, QEvent.TouchCancel):
            pts = ev.points()
            pos = pts[0].position() if pts else QPointF()
            self._end_drag(pos)
            return True
        return super().event(ev)

    def mousePressEvent(self, ev) -> None:  # noqa: N802
        if ev.button() == Qt.LeftButton:
            self._begin_drag(ev.position())
        super().mousePressEvent(ev)

    def mouseMoveEvent(self, ev) -> None:  # noqa: N802
        if ev.buttons() & Qt.LeftButton:
            self._update_drag(ev.position())
        super().mouseMoveEvent(ev)

    def mouseReleaseEvent(self, ev) -> None:  # noqa: N802
        if ev.button() == Qt.LeftButton:
            self._end_drag(ev.position())
        super().mouseReleaseEvent(ev)

    def _animate_to(self, pos: QPoint, *, mode: str) -> None:
        self._anim_mode = mode
        self._anim.stop()
        self._anim.setStartValue(self.pos())
        self._anim.setEndValue(pos)
        self._anim.start()

    def _animate_swipe_out(self, direction: int) -> None:
        end_x = self._target_pos.x() + direction * (self.width() + 80)
        end = QPoint(end_x, self._target_pos.y())
        self._timer.stop()
        self._animate_to(end, mode="hide")

    def _recompute_target(self) -> None:
        if self._parent_width <= 0 or self._parent_height <= 0:
            return
        width = max(260, min(self._parent_width - self._side_margin * 2, 740))
        self.setFixedWidth(width)
        self.adjustSize()

        x = max(self._side_margin, (self._parent_width - self.width()) // 2)
        y = max(0, self._parent_height - self.height() - self._bottom_margin)
        self._target_pos = QPoint(x, y)

    def _retarget(self) -> None:
        if not self.isVisible():
            return
        if self._anim.state() == QAbstractAnimation.Running:
            self._animate_to(self._target_pos, mode="show")
        else:
            self.move(self._target_pos)

    def _begin_drag(self, pos: QPointF) -> None:
        if not self.isVisible():
            return
        self._drag_start = pos
        self._dragging = False
        self._remaining_ms = max(self._timer.remainingTime(), 0) or self._remaining_ms
        self._timer.stop()

    def _update_drag(self, pos: QPointF) -> None:
        if self._drag_start is None or not self.isVisible():
            return
        dx = pos.x() - self._drag_start.x()
        dy = pos.y() - self._drag_start.y()
        if abs(dx) < 2 and abs(dy) < 2:
            return
        self._dragging = True
        self.move(int(self._target_pos.x() + dx), self._target_pos.y())

    def _end_drag(self, pos: QPointF) -> None:
        if self._drag_start is None:
            return
        dx = pos.x() - self._drag_start.x()
        dy = pos.y() - self._drag_start.y()
        self._drag_start = None

        threshold = 70
        if self._dragging and abs(dx) > abs(dy) and abs(dx) > threshold:
            self._animate_swipe_out(1 if dx > 0 else -1)
            self._dragging = False
            return

        if self._remaining_ms:
            self._timer.start(self._remaining_ms)
        else:
            self._timer.start(3500)
        self._animate_to(self._target_pos, mode="show")
        self._dragging = False

    def _on_anim_finished(self) -> None:
        if self._anim_mode == "hide":
            self.hide()
            if callable(self._on_closed):
                try:
                    self._on_closed()
                except Exception:
                    pass
        self._anim_mode = "idle"


class NotificationStack(QWidget):
    """Manages multiple stacked notification toasts with eviction."""

    def __init__(
        self,
        *,
        parent: QWidget | None = None,
        theme: Theme | None = None,
        max_toasts: int = 3,
        base_margin: int = 18,
        gap: int = 10,
    ) -> None:
        super().__init__(parent)
        self._theme = theme or get_theme(None)
        self._max_toasts = max(1, max_toasts)
        self._base_margin = base_margin
        self._gap = gap
        self._parent_width = 0
        self._parent_height = 0
        self._toasts: list[NotificationToast] = []
        self.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        self.hide()

    def apply_theme(self, theme: Theme) -> None:
        self._theme = theme
        for t in self._toasts:
            t.apply_theme(theme)

    def set_bounds(self, width: int, height: int) -> None:
        self._parent_width = width
        self._parent_height = height
        for t in self._toasts:
            t.set_bounds(width, height)
        self._reflow()

    def show_notification(self, app: str, summary: str, body: str, duration_ms: int | None = None) -> None:
        if len(self._toasts) >= self._max_toasts:
            oldest = self._toasts.pop(0)
            oldest.hide_toast()
        toast = NotificationToast(parent=self.parent(), theme=self._theme)
        toast.set_on_closed(lambda t=toast: self._remove_toast(t))
        toast.set_bounds(self._parent_width, self._parent_height)
        self._toasts.append(toast)
        toast.show_notification(app, summary, body, duration_ms)
        self._reflow()
        self.show()

    def _remove_toast(self, toast: NotificationToast) -> None:
        if toast in self._toasts:
            self._toasts.remove(toast)
            self._reflow()
        if not self._toasts:
            self.hide()

    def _reflow(self) -> None:
        offset = self._base_margin
        # newest at bottom (end of list)
        for toast in reversed(self._toasts):
            toast.set_bottom_margin(offset)
            offset += toast.height() + self._gap


class OnboardingOverlay(QWidget):
    """Simple multi-step onboarding overlay shown on startup."""

    def __init__(
        self,
        *,
        parent: QWidget | None = None,
        theme: Theme | None = None,
        on_finished: Callable[[], None] | None = None,
    ) -> None:
        super().__init__(parent)
        self._theme = theme or get_theme(None)
        self._on_finished = on_finished
        self._steps: list[tuple[str, str]] = [
            ("Welcome to TouchDeck", "A quick tour so you know what to expect."),
            ("Alpha software", "TouchDeck is alpha software while we move fast and polish things."),
            ("Linux-first", "TouchDeck is designed linux-first, so other platforms may need extra tweaks."),
            ("Swipe between pages", "Swipe left and right anywhere on the deck to switch pages."),
            ("Quick actions", "Swipe up from the bottom edge to view quick actions you have pinned."),
        ]
        self._index = 0

        self.setAttribute(Qt.WA_StyledBackground, True)
        self.setVisible(False)

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)
        root.addStretch(1)

        self._card = Card(radius=18, parent=self, theme=self._theme)
        body = self._card.body
        body.setSpacing(12)

        self._progress = QLabel("")
        self._progress.setObjectName("Subtle")
        self._title = QLabel("")
        self._title.setWordWrap(True)
        self._description = QLabel("")
        self._description.setWordWrap(True)

        buttons = QHBoxLayout()
        buttons.setContentsMargins(0, 6, 0, 0)
        buttons.setSpacing(10)
        buttons.addStretch(1)
        self._skip = QPushButton("Skip")
        self._next = QPushButton("Next")
        buttons.addWidget(self._skip)
        buttons.addWidget(self._next)

        body.addWidget(self._progress)
        body.addWidget(self._title)
        body.addWidget(self._description)
        body.addStretch(1)
        body.addLayout(buttons)

        root.addWidget(self._card, alignment=Qt.AlignCenter)
        root.addStretch(1)

        self._skip.clicked.connect(self._finish)
        self._next.clicked.connect(self._advance)

        self.apply_theme(self._theme)

    def set_bounds(self, width: int, height: int) -> None:
        self.setGeometry(0, 0, width, height)
        self._resize_card(width)

    def start(self) -> None:
        self._index = 0
        self._update_step()
        self.show()
        self.raise_()

    def apply_theme(self, theme: Theme) -> None:
        self._theme = theme
        self._card.apply_theme(theme)
        self.setStyleSheet("background: rgba(0, 0, 0, 160);")
        self._progress.setStyleSheet(f"color: {theme.subtle}; font-size: 14px; font-weight: 700;")
        self._title.setStyleSheet("font-size: 26px; font-weight: 800;")
        self._description.setStyleSheet(f"font-size: 17px; color: {theme.subtle};")
        self._style_buttons()
        self._resize_card(self.width())

    def _style_buttons(self) -> None:
        self._skip.setStyleSheet(
            f"""
            QPushButton {{
                padding: 10px 16px;
                border-radius: 12px;
                background: {self._theme.neutral};
                color: {self._theme.text};
                font-weight: 650;
            }}
            QPushButton:pressed {{
                background: {self._theme.neutral_pressed};
            }}
            """
        )
        self._next.setStyleSheet(
            f"""
            QPushButton {{
                padding: 10px 16px;
                border-radius: 12px;
                background: {self._theme.accent};
                color: {self._theme.background};
                font-weight: 700;
            }}
            QPushButton:pressed {{
                background: {self._theme.accent_pressed};
            }}
            """
        )

    def _advance(self) -> None:
        if self._index + 1 >= len(self._steps):
            self._finish()
            return
        self._index += 1
        self._update_step()

    def _finish(self) -> None:
        self.hide()
        if callable(self._on_finished):
            self._on_finished()

    def _update_step(self) -> None:
        title, desc = self._steps[self._index]
        self._progress.setText(f"{self._index + 1} / {len(self._steps)}")
        self._title.setText(title)
        self._description.setText(desc)
        self._next.setText("Done" if self._index == len(self._steps) - 1 else "Next")

    def _resize_card(self, width: int) -> None:
        # Keep a bit of breathing room on the edges when covering the whole window.
        target = max(320, width - 120)
        self._card.setFixedWidth(target)

class StatRow(QWidget):
    def __init__(self, label: str, parent: QWidget | None = None, theme: Theme | None = None) -> None:
        super().__init__(parent)
        self._theme = theme or get_theme(None)
        self._label = QLabel(label)
        self._value = QLabel("--")
        self._label.setStyleSheet("font-size: 16px;")
        self._value.setStyleSheet(f"font-size: 16px; color: {self._theme.text};")
        self._value.setAlignment(Qt.AlignRight | Qt.AlignVCenter)

        self._bar = QProgressBar()
        self._bar.setRange(0, 100)
        self._bar.setValue(0)
        self._bar.setTextVisible(False)
        self._bar.setFixedHeight(6)

        top = QHBoxLayout()
        top.setContentsMargins(0, 0, 0, 0)
        top.addWidget(self._label, 1)
        top.addWidget(self._value, 0)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(10)
        lay.addLayout(top)
        lay.addWidget(self._bar)

    def set_percent(self, pct: float, value_text: str) -> None:
        pct = max(0.0, min(100.0, float(pct)))
        self._bar.setValue(int(round(pct)))
        self._value.setText(value_text)

    def apply_theme(self, theme: Theme) -> None:
        self._theme = theme
        self._value.setStyleSheet(f"font-size: 16px; color: {self._theme.text};")
        self.update()
