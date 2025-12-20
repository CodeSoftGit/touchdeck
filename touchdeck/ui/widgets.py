from __future__ import annotations

from PySide6.QtCore import Qt, QSize, QRectF, QVariantAnimation, QAbstractAnimation
from PySide6.QtGui import QColor, QPainter, QPainterPath, QPen, QFontMetrics
from PySide6.QtWidgets import (
    QWidget,
    QPushButton,
    QLabel,
    QHBoxLayout,
    QVBoxLayout,
    QProgressBar,
    QGraphicsDropShadowEffect,
)

from touchdeck.animations import easing_curve
from touchdeck.themes import Theme, get_theme


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
