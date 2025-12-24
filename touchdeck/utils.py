from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from PySide6.QtCore import QUrl


def clamp(v: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, v))


def ms_to_mmss(ms: int) -> str:
    ms = max(ms, 0)
    total_sec = ms // 1000
    m = total_sec // 60
    s = total_sec % 60
    return f"{m}:{s:02d}"


def unvariant(x: Any) -> Any:
    # dbus-next variants have a `.value`
    return getattr(x, "value", x)


def first_str(x: Any) -> str:
    x = unvariant(x)
    if x is None:
        return ""
    if isinstance(x, (list, tuple)):
        return str(x[0]) if x else ""
    return str(x)


def to_local_path(uri: str) -> str:
    return QUrl(uri).toLocalFile()


@dataclass(slots=True)
class MediaState:
    """Provider-agnostic media snapshot used by the UI."""

    source: str = "mpris"  # e.g. mpris | spotify
    title: str = "Nothing Playing"
    artist: str = ""
    album: str = ""
    art_url: str | None = None
    is_playing: bool = False
    progress_ms: int = 0
    duration_ms: int = 0
    device_name: str = ""
    volume_percent: int | None = None
    can_seek: bool = False
    can_control: bool = False
    track_id: str | None = None
    bus_name: str = ""  # kept for compatibility with MPRIS custom actions
    status: str = "Stopped"
    message: str = ""

    @property
    def position_ms(self) -> int:
        return self.progress_ms

    @property
    def length_ms(self) -> int:
        return self.duration_ms


# Backwards compatibility for existing imports/type hints
NowPlaying = MediaState
