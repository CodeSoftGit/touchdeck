from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path

from touchdeck.themes import DEFAULT_THEME_KEY, THEMES


_CONFIG_PATH = Path.home() / ".config" / "touchdeck" / "settings.json"


@dataclass(slots=True)
class Settings:
    enable_gpu_stats: bool = True
    clock_24h: bool = False
    show_clock_seconds: bool = False
    music_poll_ms: int = 500
    stats_poll_ms: int = 1000
    ui_opacity_percent: int = 90  # applied to window for a gentle dim effect
    theme: str = DEFAULT_THEME_KEY


def _coerce_bool(val, default: bool) -> bool:
    if isinstance(val, bool):
        return val
    return default


def _coerce_int(val, default: int, lo: int, hi: int) -> int:
    try:
        num = int(val)
    except Exception:
        return default
    return max(lo, min(hi, num))


def _coerce_theme(val: str) -> str:
    if isinstance(val, str) and val in THEMES:
        return val
    return DEFAULT_THEME_KEY


def load_settings() -> Settings:
    if not _CONFIG_PATH.exists():
        return Settings()
    try:
        data = json.loads(_CONFIG_PATH.read_text())
    except Exception:
        return Settings()

    return Settings(
        enable_gpu_stats=_coerce_bool(data.get("enable_gpu_stats"), True),
        clock_24h=_coerce_bool(data.get("clock_24h"), False),
        show_clock_seconds=_coerce_bool(data.get("show_clock_seconds"), False),
        music_poll_ms=_coerce_int(data.get("music_poll_ms"), 500, 250, 3000),
        stats_poll_ms=_coerce_int(data.get("stats_poll_ms"), 1000, 500, 5000),
        ui_opacity_percent=_coerce_int(data.get("ui_opacity_percent"), 90, 50, 100),
        theme=_coerce_theme(data.get("theme")),
    )


def save_settings(s: Settings) -> None:
    _CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    _CONFIG_PATH.write_text(json.dumps(asdict(s), indent=2))
