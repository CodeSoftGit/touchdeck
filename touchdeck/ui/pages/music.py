# /pages/music.py
from __future__ import annotations

import base64
from urllib.parse import unquote_to_bytes

from PySide6.QtCore import Qt, QTimer, QUrl
from PySide6.QtGui import QPainter, QPainterPath, QPixmap
from PySide6.QtNetwork import QNetworkAccessManager, QNetworkRequest
from PySide6.QtWidgets import QLabel, QHBoxLayout, QSlider, QVBoxLayout, QWidget

from touchdeck.utils import NowPlaying, ms_to_mmss
from touchdeck.LRCLIB import SyncedLyrics
from touchdeck.ui.widgets import Card, IconButton, ElideLabel, MultiLineElideLabel
from touchdeck.themes import Theme


_DATA_URL_MAX_DECODED_BYTES = 3_000_000  # avoid nuking RAM if a provider goes wild
_HTTP_ART_TIMEOUT_MS = 7000


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


def _pixmap_from_data_url(url: str) -> QPixmap:
    """
    Decode a data: URL into a QPixmap.

    Supports:
      - data:<mime>;base64,<...>
      - data:<mime>,<urlencoded bytes>
    """
    pix = QPixmap()
    if not url.startswith("data:"):
        return pix

    try:
        header, payload = url.split(",", 1)
    except ValueError:
        return pix

    is_base64 = ";base64" in header.lower()
    try:
        if is_base64:
            raw = base64.b64decode(payload, validate=False)
        else:
            raw = unquote_to_bytes(payload)
    except Exception:
        return pix

    if len(raw) > _DATA_URL_MAX_DECODED_BYTES:
        return QPixmap()

    pix.loadFromData(raw)
    return pix


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

        # Qt 6.7+ has QNetworkAccessManager.sslErrors; guard for older builds. :contentReference[oaicite:3]{index=3}
        if hasattr(self._net, "sslErrors"):
            self._net.sslErrors.connect(self._on_ssl_errors)  # type: ignore[attr-defined]

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

        self.title.setText(np.title or "Nothing Playing")
        self.artist.setText(np.artist or "")

        playing = getattr(np, "is_playing", False) or np.status == "Playing"
        self.btn_play.kind = "pause" if playing else "play"
        self.btn_play.update()

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

        self._set_art(np.art_url)

    def set_synced_lyrics(self, lyrics: SyncedLyrics | None) -> None:
        self._lyrics = lyrics
        self._lyrics_message_timer.stop()
        self._set_lyric_line("")

    def show_lyrics_message(self, text: str, duration_ms: int) -> None:
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

        # 1) data: URLs are NOT something you should send through QNetworkAccessManager.
        #    Decode locally and feed bytes to QPixmap.loadFromData(). :contentReference[oaicite:4]{index=4}
        if url.startswith("data:"):
            pix = _pixmap_from_data_url(url)
            self._apply_pix(pix)
            if pix.isNull():
                print(f"[MusicPage] data-url decode failed (len={len(url)})")
            return

        qurl = QUrl(url)
        if not qurl.isValid():
            print(f"[MusicPage] invalid art URL: {url!r}")
            self.art.setPixmap(QPixmap())
            self.art.setText("♪")
            return

        if qurl.isLocalFile() or url.startswith("file://"):
            path = qurl.toLocalFile()
            pix = QPixmap(path)
            self._apply_pix(pix)
            return

        # 2) HTTP(S) fetch
        req = QNetworkRequest(qurl)

        # Redirect handling: be explicit. Qt 6 changed default redirect policy and behavior. :contentReference[oaicite:5]{index=5}
        try:
            if hasattr(QNetworkRequest, "RedirectPolicyAttribute") and hasattr(
                QNetworkRequest, "NoLessSafeRedirectPolicy"
            ):
                req.setAttribute(
                    QNetworkRequest.RedirectPolicyAttribute,
                    QNetworkRequest.NoLessSafeRedirectPolicy,
                )
        except Exception:
            pass

        # Some older code uses FollowRedirectsAttribute (Qt 5). Keep it if present.
        try:
            if hasattr(QNetworkRequest, "FollowRedirectsAttribute"):
                req.setAttribute(QNetworkRequest.FollowRedirectsAttribute, True)
        except Exception:
            pass

        # Timeouts (Qt 6.7+: DefaultTransferTimeout exists; otherwise ignore)
        try:
            if hasattr(QNetworkRequest, "DefaultTransferTimeout"):
                req.setTransferTimeout(_HTTP_ART_TIMEOUT_MS)  # type: ignore[attr-defined]
        except Exception:
            pass

        # Many CDNs behave better with a UA.
        try:
            req.setRawHeader(b"User-Agent", b"touchdeck/qt-network")
            req.setRawHeader(b"Accept", b"image/*")
        except Exception:
            pass

        reply = self._net.get(req)
        # Tag this reply with the URL we requested, so we can ignore stale replies.
        try:
            reply.setProperty("_touchdeck_art_url", url)
        except Exception:
            pass

    def _on_ssl_errors(self, reply, errors) -> None:
        # Do NOT ignore SSL errors silently; log them so you know what’s wrong. :contentReference[oaicite:6]{index=6}
        try:
            req_url = reply.property("_touchdeck_art_url")
        except Exception:
            req_url = None
        msgs = []
        try:
            for e in errors:
                msgs.append(str(getattr(e, "errorString", lambda: e)()))
        except Exception:
            pass
        print(f"[MusicPage] SSL errors for {req_url!r}: {msgs}")

    def _on_art_reply(self, reply) -> None:
        # Ignore replies that are not for the currently requested art URL.
        try:
            req_url = reply.property("_touchdeck_art_url")
        except Exception:
            req_url = None

        if req_url and req_url != self._current_art_url:
            reply.deleteLater()
            return

        # Redirects are not errors; you must either set redirect policy or handle manually. :contentReference[oaicite:7]{index=7}
        try:
            redir = reply.attribute(QNetworkRequest.RedirectionTargetAttribute)
            if isinstance(redir, QUrl) and redir.isValid():
                new_url = reply.url().resolved(redir)
                new_url_str = new_url.toString()
                if new_url_str and new_url_str != self._current_art_url:
                    print(f"[MusicPage] redirect {self._current_art_url!r} -> {new_url_str!r}")
                    # Update current and re-request
                    self._current_art_url = new_url_str
                    reply.deleteLater()
                    self._set_art(new_url_str)
                    return
        except Exception:
            pass

        # Log errors instead of silently doing nothing.
        if reply.error():
            try:
                status = reply.attribute(QNetworkRequest.HttpStatusCodeAttribute)
            except Exception:
                status = None
            try:
                err_str = reply.errorString()
            except Exception:
                err_str = "unknown error"
            print(f"[MusicPage] art fetch failed url={self._current_art_url!r} status={status!r} err={err_str!r}")
            reply.deleteLater()
            return

        data = reply.readAll()
        pix = QPixmap()
        ok = pix.loadFromData(bytes(data))
        if not ok or pix.isNull():
            try:
                status = reply.attribute(QNetworkRequest.HttpStatusCodeAttribute)
            except Exception:
                status = None
            print(
                f"[MusicPage] art decode failed url={self._current_art_url!r} "
                f"status={status!r} bytes={len(bytes(data))}"
            )
            self._apply_pix(QPixmap())
            reply.deleteLater()
            return

        self._apply_pix(pix)
        reply.deleteLater()

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
