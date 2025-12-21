from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable


@dataclass(frozen=True)
class QuickActionOption:
    key: str
    label: str
    description: str
    is_custom: bool = False


@dataclass(frozen=True)
class CustomQuickAction:
    key: str
    title: str
    command: str
    timeout_ms: int


AVAILABLE_QUICK_ACTIONS = [
    QuickActionOption(
        "play_pause", "Play/Pause", "Toggle playback for the current player"
    ),
    QuickActionOption("next_track", "Next Track", "Skip to the next song"),
    QuickActionOption("prev_track", "Previous Track", "Go back to the last song"),
    QuickActionOption("run_speedtest", "Run Speed Test", "Start a new speed test"),
    QuickActionOption(
        "toggle_gpu", "Toggle GPU Stats", "Enable or disable GPU monitoring"
    ),
]

DEFAULT_QUICK_ACTION_KEYS = ["play_pause", "next_track", "run_speedtest"]
DEFAULT_CUSTOM_ACTION_TIMEOUT_MS = 8000

_VALID_ACTION_KEYS = {opt.key for opt in AVAILABLE_QUICK_ACTIONS}


def quick_action_lookup(
    custom_actions: Iterable[CustomQuickAction] | None = None,
) -> dict[str, QuickActionOption]:
    options = {opt.key: opt for opt in AVAILABLE_QUICK_ACTIONS}
    for action in custom_actions or []:
        if (
            isinstance(action, CustomQuickAction)
            and action.key
            and action.key not in options
        ):
            options[action.key] = QuickActionOption(
                action.key, action.title, action.command, is_custom=True
            )
    return options


def ordered_quick_action_options(
    custom_actions: Iterable[CustomQuickAction] | None = None,
) -> list[QuickActionOption]:
    options = list(AVAILABLE_QUICK_ACTIONS)
    for action in custom_actions or []:
        if isinstance(action, CustomQuickAction) and action.key:
            options.append(
                QuickActionOption(
                    action.key, action.title, action.command, is_custom=True
                )
            )
    return options


def generate_custom_action_key(title: str, existing: Iterable[str]) -> str:
    slug = "".join(c if c.isalnum() else "-" for c in (title or "").strip().lower())
    slug = "-".join([part for part in slug.split("-") if part]) or "action"
    base = f"custom-{slug}"
    used = set(existing)
    if base not in used:
        return base
    idx = 2
    while f"{base}-{idx}" in used:
        idx += 1
    return f"{base}-{idx}"


def filter_quick_action_keys(
    keys: Iterable[str] | None,
    custom_actions: Iterable[CustomQuickAction] | None = None,
) -> list[str]:
    """Keep only known action keys, preserve order, and drop duplicates."""
    seen: set[str] = set()
    result: list[str] = []
    custom_keys = {
        action.key
        for action in (custom_actions or [])
        if isinstance(action, CustomQuickAction) and action.key
    }
    valid_keys = _VALID_ACTION_KEYS | custom_keys
    if keys is not None:
        for key in keys:
            if not isinstance(key, str):
                continue
            if key in valid_keys and key not in seen:
                result.append(key)
                seen.add(key)
    if not result:
        result = list(DEFAULT_QUICK_ACTION_KEYS)
    return result
