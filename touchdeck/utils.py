from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from PySide6.QtCore import QUrl


def clamp(v: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, v))


def ms_to_mmss(ms: int) -> str:
    if ms < 0:
        ms = 0
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
class NowPlaying:
    bus_name: str = ""
    status: str = "Stopped"
    title: str = "Nothing Playing"
    artist: str = ""
    album: str = ""
    art_url: str | None = None
    position_ms: int = 0
    length_ms: int = 0
    can_seek: bool = False
    track_id: str | None = None  # D-Bus object path
