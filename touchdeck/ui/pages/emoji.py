from __future__ import annotations

from functools import partial
from pathlib import Path

from PySide6.QtCore import QSize, Qt, QTimer
from PySide6.QtGui import QGuiApplication, QIcon
from PySide6.QtWidgets import QGridLayout, QLabel, QPushButton, QVBoxLayout, QWidget

from touchdeck.themes import Theme, get_theme
from touchdeck.ui.widgets import Card


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

    def __init__(
        self, parent: QWidget | None = None, theme: Theme | None = None
    ) -> None:
        super().__init__(parent)
        self._theme = theme or get_theme(None)
        self.card = Card(theme=self._theme)
        self._buttons: list[QPushButton] = []
        self._emoji_root = Path(__file__).resolve().parents[2] / "emojis"
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
        self._toast.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)

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
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
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
