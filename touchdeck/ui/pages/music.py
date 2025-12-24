from __future__ import annotations

from PySide6.QtCore import Qt, QTimer, QUrl
from PySide6.QtGui import QPainter, QPainterPath, QPixmap
from PySide6.QtNetwork import QNetworkAccessManager, QNetworkRequest
from PySide6.QtWidgets import QLabel, QHBoxLayout, QSlider, QVBoxLayout, QWidget

from touchdeck.utils import NowPlaying, ms_to_mmss
from touchdeck.LRCLIB import SyncedLyrics
from touchdeck.ui.widgets import Card, IconButton, ElideLabel, MultiLineElideLabel
from touchdeck.themes import Theme


def _rounded_pixmap(src: QPixmap, size: int, radius: int) -> QPixmap:
    if src.isNull():
        return QPixmap()
    scaled = src.scaled(
        size, size, Qt.KeepAspectRatioByExpanding, Qt.SmoothTransformation
    )
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


class MusicPage(QWidget):
    def __init__(self, theme: Theme, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._theme = theme
        self._np: NowPlaying | None = None
        self._lyrics: SyncedLyrics | None = None
        self._seeking = False
        self._lyrics_message_timer = QTimer(self)
        self._lyrics_message_timer.setSingleShot(True)
        self._lyrics_message_timer.timeout.connect(lambda: self._set_lyric_line(""))

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

        self.lyric_line = MultiLineElideLabel("", max_lines=3, mode=Qt.ElideRight)
        self.lyric_line.setObjectName("Subtle")
        self.lyric_line.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        self.lyric_line.setVisible(False)
        self._apply_lyrics_style()

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
        text_col.addWidget(self.lyric_line)
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
        self._apply_lyrics_style()
        self.update()

    def set_now_playing(self, np: NowPlaying) -> None:
        self._np = np

        # More "deck-y": keep text stable, avoid flickering empty
        self.title.setText(np.title or "Nothing Playing")
        self.artist.setText(np.artist or "")

        # Update play/pause icon
        playing = getattr(np, "is_playing", False) or np.status == "Playing"
        self.btn_play.kind = "pause" if playing else "play"
        self.btn_play.update()

        # Update slider
        length = max(1, int(np.length_ms or 1))
        self.slider.setRange(0, length)
        if not self._seeking:
            self.slider.setValue(int(np.position_ms or 0))

        self.t_left.setText(ms_to_mmss(int(np.position_ms or 0)))
        self.t_right.setText(ms_to_mmss(int(np.length_ms or 0)))

        lyric = ""
        if self._lyrics is not None:
            lyric = self._lyrics.line_at(int(np.position_ms or 0))
        self._set_lyric_line(lyric)

        # Artwork
        self._set_art(np.art_url)

    def set_synced_lyrics(self, lyrics: SyncedLyrics | None) -> None:
        self._lyrics = lyrics
        self._lyrics_message_timer.stop()
        self._set_lyric_line("")

    def show_lyrics_message(self, text: str, duration_ms: int) -> None:
        """Show a temporary lyrics message and clear it after the timeout."""
        self._lyrics_message_timer.stop()
        self._set_lyric_line(text)
        self._lyrics_message_timer.start(max(0, duration_ms))

    def _set_lyric_line(self, text: str) -> None:
        text = text.strip()
        self.lyric_line.setText(text)
        self.lyric_line.setVisible(bool(text))

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

    def _apply_lyrics_style(self) -> None:
        self.lyric_line.setStyleSheet(
            f"""
            QLabel {{
                font-size: 17px;
                font-style: italic;
                font-weight: 600;
                padding: 4px 10px;
                border-radius: 10px;
                background: {self._theme.neutral};
                color: {self._theme.text};
                border: 1px solid {self._theme.panel_border};
            }}
            """
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
