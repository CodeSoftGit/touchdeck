from __future__ import annotations

from touchdeck import themes


def test_get_theme_falls_back_to_default() -> None:
    default_theme = themes.THEMES[themes.DEFAULT_THEME_KEY]

    assert themes.get_theme("nonexistent").key == default_theme.key
    assert themes.get_theme(None).key == default_theme.key


def test_build_qss_includes_theme_colors() -> None:
    theme = themes.THEMES["sunset"]

    qss = themes.build_qss(theme)

    assert theme.background in qss
    assert theme.accent in qss
