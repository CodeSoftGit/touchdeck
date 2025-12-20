from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path

from touchdeck.themes import DEFAULT_THEME_KEY, THEMES
from touchdeck.quick_actions import DEFAULT_QUICK_ACTION_KEYS, filter_quick_action_keys


_CONFIG_PATH = Path.home() / ".config" / "touchdeck" / "settings.json"
DEFAULT_PAGE_KEYS = ["music", "stats", "clock", "emoji", "speedtest", "settings"]


@dataclass(slots=True)
class Settings:
    enable_gpu_stats: bool = True
    clock_24h: bool = False
    show_clock_seconds: bool = False
    onboarding_completed: bool = False
    music_poll_ms: int = 500
    stats_poll_ms: int = 1000
    ui_opacity_percent: int = 90  # applied to window for a gentle dim effect
    theme: str = DEFAULT_THEME_KEY
    quick_actions: list[str] = field(default_factory=lambda: list(DEFAULT_QUICK_ACTION_KEYS))
    preferred_display: str | None = None
    demo_mode: bool = False
    display_selected: bool = False
    enabled_pages: list[str] = field(default_factory=lambda: list(DEFAULT_PAGE_KEYS))


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


def _coerce_quick_actions(val) -> list[str]:
    if isinstance(val, list):
        return filter_quick_action_keys(val)
    return filter_quick_action_keys(None)


def _coerce_optional_str(val) -> str | None:
    if isinstance(val, str):
        return val
    return None


def _coerce_enabled_pages(val) -> list[str]:
    if isinstance(val, list):
        pages = [p for p in val if isinstance(p, str) and p in DEFAULT_PAGE_KEYS]
    else:
        pages = []
    if not pages:
        pages = list(DEFAULT_PAGE_KEYS)
    if "settings" not in pages:
        pages.append("settings")
    # preserve default ordering
    ordered = [p for p in DEFAULT_PAGE_KEYS if p in pages]
    for p in pages:
        if p not in ordered:
            ordered.append(p)
    return ordered


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
        onboarding_completed=_coerce_bool(data.get("onboarding_completed"), False),
        music_poll_ms=_coerce_int(data.get("music_poll_ms"), 500, 250, 3000),
        stats_poll_ms=_coerce_int(data.get("stats_poll_ms"), 1000, 500, 5000),
        ui_opacity_percent=_coerce_int(data.get("ui_opacity_percent"), 90, 50, 100),
        theme=_coerce_theme(data.get("theme")),
        quick_actions=_coerce_quick_actions(data.get("quick_actions")),
        preferred_display=_coerce_optional_str(data.get("preferred_display")),
        demo_mode=_coerce_bool(data.get("demo_mode"), False),
        display_selected=_coerce_bool(data.get("display_selected"), False),
        enabled_pages=_coerce_enabled_pages(data.get("enabled_pages")),
    )


def save_settings(s: Settings) -> None:
    _CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    _CONFIG_PATH.write_text(json.dumps(asdict(s), indent=2))


def reset_settings() -> None:
    if _CONFIG_PATH.exists():
        _CONFIG_PATH.unlink()
