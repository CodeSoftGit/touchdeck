from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from touchdeck.themes import DEFAULT_THEME_KEY, THEMES
from touchdeck.quick_actions import (
    DEFAULT_CUSTOM_ACTION_TIMEOUT_MS,
    DEFAULT_QUICK_ACTION_KEYS,
    CustomQuickAction,
    filter_quick_action_keys,
)


_CONFIG_PATH = Path.home() / ".config" / "touchdeck" / "settings.json"
DEFAULT_PAGE_KEYS = [
    "music",
    "stats",
    "clock",
    "emoji",
    "speedtest",
    "developer",
    "settings",
]
DEFAULT_ENABLED_PAGE_KEYS = [
    "music",
    "stats",
    "clock",
    "emoji",
    "speedtest",
    "settings",
]


@dataclass(slots=True)
class Settings:
    media_source: str = "mpris"
    spotify_client_id: str = ""
    spotify_client_secret: str = ""
    spotify_redirect_port: int = 8765
    spotify_device_id: str | None = None
    enable_gpu_stats: bool = True
    clock_24h: bool = False
    show_clock_seconds: bool = False
    onboarding_completed: bool = False
    music_poll_ms: int = 500
    stats_poll_ms: int = 1000
    ui_opacity_percent: int = 90  # applied to window for a gentle dim effect
    ui_scale_percent: int = 100
    theme: str = DEFAULT_THEME_KEY
    quick_actions: list[str] = field(
        default_factory=lambda: list(DEFAULT_QUICK_ACTION_KEYS)
    )
    custom_actions: list[CustomQuickAction] = field(default_factory=list)
    preferred_display: str | None = None
    demo_mode: bool = False
    display_selected: bool = False
    enabled_pages: list[str] = field(
        default_factory=lambda: list(DEFAULT_ENABLED_PAGE_KEYS)
    )
    lyrics_cache: dict[str, list[dict[str, Any]]] = field(default_factory=dict)


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


def _coerce_media_source(val: str) -> str:
    if isinstance(val, str) and val.lower() in ("mpris", "spotify"):
        return val.lower()
    return "mpris"


def _coerce_quick_actions(
    val, custom_actions: list[CustomQuickAction] | None
) -> list[str]:
    if isinstance(val, list):
        return filter_quick_action_keys(val, custom_actions)
    return filter_quick_action_keys(None, custom_actions)


def _coerce_custom_actions(val) -> list[CustomQuickAction]:
    if not isinstance(val, list):
        return []
    seen: set[str] = set()
    actions: list[CustomQuickAction] = []
    for entry in val:
        if not isinstance(entry, dict):
            continue
        key = entry.get("key")
        title = entry.get("title")
        command = entry.get("command")
        if not isinstance(key, str) or not key:
            continue
        if not isinstance(title, str) or not title:
            continue
        if not isinstance(command, str) or not command:
            continue
        if key in seen:
            continue
        timeout_ms = _coerce_int(
            entry.get("timeout_ms"),
            DEFAULT_CUSTOM_ACTION_TIMEOUT_MS,
            500,
            300_000,
        )
        actions.append(
            CustomQuickAction(
                key=key, title=title, command=command, timeout_ms=timeout_ms
            )
        )
        seen.add(key)
    return actions


def _coerce_optional_str(val) -> str | None:
    if isinstance(val, str):
        return val
    return None


def _coerce_port(val, default: int = 8765) -> int:
    num = _coerce_int(val, default, 1024, 65535)
    return num


def _coerce_enabled_pages(val) -> list[str]:
    if isinstance(val, list):
        pages = [p for p in val if isinstance(p, str) and p in DEFAULT_PAGE_KEYS]
    else:
        pages = []
    if not pages:
        pages = list(DEFAULT_ENABLED_PAGE_KEYS)
    if "settings" not in pages:
        pages.append("settings")
    # preserve default ordering
    ordered = [p for p in DEFAULT_PAGE_KEYS if p in pages]
    for p in pages:
        if p not in ordered:
            ordered.append(p)
    return ordered


def _coerce_lyrics_cache(val: Any) -> dict[str, list[dict[str, Any]]]:
    if not isinstance(val, dict):
        return {}
    cache: dict[str, list[dict[str, Any]]] = {}
    for key, lines in val.items():
        if not isinstance(key, str) or not isinstance(lines, list):
            continue
        entries: list[dict[str, Any]] = []
        for entry in lines:
            if not isinstance(entry, dict):
                continue
            at_ms = entry.get("at_ms")
            text = entry.get("text")
            if not isinstance(at_ms, int) or at_ms < 0:
                continue
            if not isinstance(text, str):
                continue
            entries.append({"at_ms": at_ms, "text": text})
        if entries:
            cache[key] = entries
    return cache


def load_settings() -> Settings:
    if not _CONFIG_PATH.exists():
        return Settings()
    try:
        data = json.loads(_CONFIG_PATH.read_text())
    except Exception:
        return Settings()

    custom_actions = _coerce_custom_actions(data.get("custom_actions"))

    return Settings(
        media_source=_coerce_media_source(data.get("media_source")),
        spotify_client_id=_coerce_optional_str(data.get("spotify_client_id")) or "",
        spotify_client_secret=_coerce_optional_str(data.get("spotify_client_secret"))
        or "",
        spotify_redirect_port=_coerce_port(data.get("spotify_redirect_port"), 8765),
        spotify_device_id=_coerce_optional_str(data.get("spotify_device_id")),
        enable_gpu_stats=_coerce_bool(data.get("enable_gpu_stats"), True),
        clock_24h=_coerce_bool(data.get("clock_24h"), False),
        show_clock_seconds=_coerce_bool(data.get("show_clock_seconds"), False),
        onboarding_completed=_coerce_bool(data.get("onboarding_completed"), False),
        music_poll_ms=_coerce_int(data.get("music_poll_ms"), 500, 250, 3000),
        stats_poll_ms=_coerce_int(data.get("stats_poll_ms"), 1000, 500, 5000),
        ui_opacity_percent=_coerce_int(data.get("ui_opacity_percent"), 90, 50, 100),
        ui_scale_percent=_coerce_int(data.get("ui_scale_percent"), 100, 25, 200),
        theme=_coerce_theme(data.get("theme")),
        quick_actions=_coerce_quick_actions(data.get("quick_actions"), custom_actions),
        custom_actions=custom_actions,
        preferred_display=_coerce_optional_str(data.get("preferred_display")),
        demo_mode=_coerce_bool(data.get("demo_mode"), False),
        display_selected=_coerce_bool(data.get("display_selected"), False),
        enabled_pages=_coerce_enabled_pages(data.get("enabled_pages")),
        lyrics_cache=_coerce_lyrics_cache(data.get("lyrics_cache")),
    )


def save_settings(s: Settings) -> None:
    _CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    _CONFIG_PATH.write_text(json.dumps(asdict(s), indent=2))


def config_dir() -> Path:
    return _CONFIG_PATH.parent


def reset_settings() -> None:
    if _CONFIG_PATH.exists():
        _CONFIG_PATH.unlink()
