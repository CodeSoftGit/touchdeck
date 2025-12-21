from __future__ import annotations

import asyncio
import json
import re
from dataclasses import dataclass
from typing import Any
from urllib.error import HTTPError
from urllib.parse import urlencode
from urllib.request import Request, urlopen


_API_URL = "https://lrclib.net/api/get"
_UA = "touchdeck-lyrics/0.1"
_TS_RE = re.compile(r"\[(\d+):(\d{2})(?:\.(\d{1,3}))?\]")


@dataclass(slots=True)
class LyricLine:
    at_ms: int
    text: str


@dataclass(slots=True)
class SyncedLyrics:
    lines: list[LyricLine]

    def line_at(self, position_ms: int) -> str:
        """Return the lyric line active at the given playback position."""
        if not self.lines or position_ms < self.lines[0].at_ms:
            return ""
        # Linear scan keeps it simple; lists are short.
        last = ""
        for line in self.lines:
            if position_ms < line.at_ms:
                break
            last = line.text
        return last


class LyricsNotFoundError(Exception):
    """Raised when the lyrics API returns 404/not found."""


def _parse_synced_lyrics(lrc_text: str) -> SyncedLyrics | None:
    lines: list[LyricLine] = []
    for raw in lrc_text.splitlines():
        stamps = _TS_RE.findall(raw)
        text = _TS_RE.sub("", raw).strip()
        if not stamps or not text:
            continue
        for m, s, frac in stamps:
            minutes = int(m)
            seconds = int(s)
            millis = int((frac or "0").ljust(3, "0"))
            at_ms = (minutes * 60 + seconds) * 1000 + millis
            lines.append(LyricLine(at_ms=at_ms, text=text))
    lines.sort(key=lambda l: l.at_ms)
    return SyncedLyrics(lines=lines) if lines else None


class LrclibClient:
    """Thin client for the LRCLIB signature lookup endpoint."""

    def __init__(self, *, base_url: str = _API_URL) -> None:
        self._base_url = base_url

    async def fetch_synced(
        self, *, track_name: str, artist_name: str, album_name: str, duration_ms: int
    ) -> SyncedLyrics | None:
        if not track_name or not artist_name or duration_ms <= 0:
            return None
        duration_s = max(1, int(round(duration_ms / 1000)))
        query = {
            "artist_name": artist_name,
            "track_name": track_name,
            "album_name": album_name or "",
            "duration": duration_s,
        }
        return await asyncio.to_thread(self._request, query)

    def _request(self, query: dict[str, Any]) -> SyncedLyrics | None:
        try:
            qs = urlencode(query)
            req = Request(f"{self._base_url}?{qs}", headers={"User-Agent": _UA})
            with urlopen(req, timeout=6) as resp:
                data = resp.read()
        except HTTPError as exc:
            if exc.code == 404:
                raise LyricsNotFoundError from exc
            return None
        except Exception:
            return None

        try:
            payload = json.loads(data.decode("utf-8"))
        except Exception:
            return None

        synced = payload.get("syncedLyrics")
        if not synced:
            return None
        return _parse_synced_lyrics(str(synced))
