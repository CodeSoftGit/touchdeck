from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Theme:
    key: str
    label: str
    background: str
    gradient_top: str
    gradient_bottom: str
    text: str
    subtle: str
    panel: str
    panel_border: str
    accent: str
    accent_pressed: str
    neutral: str
    neutral_hover: str
    neutral_pressed: str
    slider_track: str
    slider_fill: str
    slider_handle: str
    progress_bg: str
    progress_chunk: str


THEMES: dict[str, Theme] = {
    "midnight": Theme(
        key="midnight",
        label="Midnight",
        background="#000000",
        gradient_top="#000000",
        gradient_bottom="#050505",
        text="#ffffff",
        subtle="#9aa0a6",
        panel="#0b0b0b",
        panel_border="#1c1c1c",
        accent="#a855f7",
        accent_pressed="#8d44d6",
        neutral="#0f0f0f",
        neutral_hover="#131313",
        neutral_pressed="#0a0a0a",
        slider_track="#2a2a2a",
        slider_fill="#a855f7",
        slider_handle="#ffffff",
        progress_bg="#2a2a2a",
        progress_chunk="#a855f7",
    ),
    "glacier": Theme(
        key="glacier",
        label="Glacier",
        background="#030a18",
        gradient_top="#071429",
        gradient_bottom="#040915",
        text="#e9f2ff",
        subtle="#9fb3d9",
        panel="#0a1424",
        panel_border="#12203a",
        accent="#5ad4e6",
        accent_pressed="#38b3c8",
        neutral="#0e1a2e",
        neutral_hover="#12233d",
        neutral_pressed="#0c1627",
        slider_track="#1a2a44",
        slider_fill="#5ad4e6",
        slider_handle="#e9f2ff",
        progress_bg="#1a2a44",
        progress_chunk="#5ad4e6",
    ),
    "sunset": Theme(
        key="sunset",
        label="Sunset",
        background="#140606",
        gradient_top="#1f0b0b",
        gradient_bottom="#120404",
        text="#fff4ec",
        subtle="#d3a79c",
        panel="#1f0f0f",
        panel_border="#2b1616",
        accent="#f97316",
        accent_pressed="#ea580c",
        neutral="#2a1414",
        neutral_hover="#311818",
        neutral_pressed="#221010",
        slider_track="#402424",
        slider_fill="#f97316",
        slider_handle="#fff4ec",
        progress_bg="#402424",
        progress_chunk="#f97316",
    ),
}

DEFAULT_THEME_KEY = "midnight"


def get_theme(key: str | None) -> Theme:
    if not key:
        return THEMES[DEFAULT_THEME_KEY]
    return THEMES.get(key, THEMES[DEFAULT_THEME_KEY])


def theme_options() -> list[Theme]:
    return list(THEMES.values())


def build_qss(theme: Theme) -> str:
    return f"""
QWidget {{
  background: {theme.background};
  color: {theme.text};
  font-family: "Inter", "SF Pro Display", "Segoe UI", "Noto Sans", sans-serif;
}}

QWidget#DeckWindow {{
  background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
    stop:0 {theme.gradient_top},
    stop:1 {theme.gradient_bottom});
}}

QLabel#Subtle {{
  color: {theme.subtle};
}}

QSlider::groove:horizontal {{
  height: 6px;
  border-radius: 3px;
  background: {theme.slider_track};
}}

QSlider::sub-page:horizontal {{
  height: 6px;
  border-radius: 3px;
  background: {theme.slider_fill};
}}

QSlider::add-page:horizontal {{
  height: 6px;
  border-radius: 3px;
  background: {theme.slider_track};
}}

QSlider::handle:horizontal {{
  width: 12px;
  height: 12px;
  margin: -4px 0;
  border-radius: 6px;
  background: {theme.slider_handle};
}}

QProgressBar {{
  border: 0px;
  background: {theme.progress_bg};
  border-radius: 3px;
  height: 6px;
}}

QProgressBar::chunk {{
  background: {theme.progress_chunk};
  border-radius: 3px;
}}
"""
