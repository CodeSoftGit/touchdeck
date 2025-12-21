from __future__ import annotations

import json

from touchdeck import settings


def test_load_settings_returns_defaults_when_file_absent(tmp_path) -> None:
    config_path = tmp_path / "settings.json"
    settings._CONFIG_PATH = config_path

    loaded = settings.load_settings()

    assert loaded == settings.Settings()


def test_load_settings_handles_invalid_file(tmp_path) -> None:
    config_path = tmp_path / "settings.json"
    config_path.write_text("{not: json")
    settings._CONFIG_PATH = config_path

    loaded = settings.load_settings()

    assert loaded == settings.Settings()


def test_save_and_load_round_trip(tmp_path) -> None:
    config_path = tmp_path / "settings.json"
    settings._CONFIG_PATH = config_path

    original = settings.Settings(
        enable_gpu_stats=False,
        clock_24h=True,
        show_clock_seconds=True,
        music_poll_ms=750,
        stats_poll_ms=1500,
        ui_opacity_percent=80,
        theme="glacier",
    )

    settings.save_settings(original)
    assert json.loads(config_path.read_text())["theme"] == "glacier"

    loaded = settings.load_settings()
    assert loaded == original


def test_load_settings_filters_quick_actions(tmp_path) -> None:
    config_path = tmp_path / "settings.json"
    settings._CONFIG_PATH = config_path
    config_path.write_text(
        json.dumps(
            {
                "custom_actions": [
                    {
                        "key": "custom-echo",
                        "title": "Echo",
                        "command": "echo hi",
                        "timeout_ms": 5000,
                    }
                ],
                "quick_actions": [
                    "play_pause",
                    "unknown",
                    "run_speedtest",
                    "play_pause",
                    "custom-echo",
                ],
            }
        )
    )

    loaded = settings.load_settings()

    assert loaded.quick_actions == ["play_pause", "run_speedtest", "custom-echo"]


def test_load_settings_filters_lyrics_cache(tmp_path) -> None:
    config_path = tmp_path / "settings.json"
    settings._CONFIG_PATH = config_path
    config_path.write_text(
        json.dumps(
            {
                "lyrics_cache": {
                    "valid": [
                        {"at_ms": 100, "text": "line1"},
                        {"at_ms": 200, "text": "line2"},
                    ],
                    "invalid": [
                        {"at_ms": "nope", "text": "bad"},
                        {"at_ms": -1, "text": "skip"},
                    ],
                    123: [{"at_ms": 300, "text": "bad key"}],
                }
            }
        )
    )

    loaded = settings.load_settings()

    assert loaded.lyrics_cache == {
        "valid": [
            {"at_ms": 100, "text": "line1"},
            {"at_ms": 200, "text": "line2"},
        ]
    }
