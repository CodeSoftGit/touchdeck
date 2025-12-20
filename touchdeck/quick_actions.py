from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable


@dataclass(frozen=True)
class QuickActionOption:
    key: str
    label: str
    description: str


AVAILABLE_QUICK_ACTIONS = [
    QuickActionOption("play_pause", "Play/Pause", "Toggle playback for the current player"),
    QuickActionOption("next_track", "Next Track", "Skip to the next song"),
    QuickActionOption("prev_track", "Previous Track", "Go back to the last song"),
    QuickActionOption("run_speedtest", "Run Speed Test", "Start a new speed test"),
    QuickActionOption("toggle_gpu", "Toggle GPU Stats", "Enable or disable GPU monitoring"),
]

DEFAULT_QUICK_ACTION_KEYS = ["play_pause", "next_track", "run_speedtest"]

_VALID_ACTION_KEYS = {opt.key for opt in AVAILABLE_QUICK_ACTIONS}


def quick_action_lookup() -> dict[str, QuickActionOption]:
    return {opt.key: opt for opt in AVAILABLE_QUICK_ACTIONS}


def filter_quick_action_keys(keys: Iterable[str] | None) -> list[str]:
    """Keep only known action keys, preserve order, and drop duplicates."""
    seen: set[str] = set()
    result: list[str] = []
    if keys is not None:
        for key in keys:
            if not isinstance(key, str):
                continue
            if key in _VALID_ACTION_KEYS and key not in seen:
                result.append(key)
                seen.add(key)
    if not result:
        result = list(DEFAULT_QUICK_ACTION_KEYS)
    return result
