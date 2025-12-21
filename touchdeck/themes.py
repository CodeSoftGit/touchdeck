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
    "dawn": Theme(
        key="dawn",
        label="Dawn",
        background="#f7f8fb",
        gradient_top="#ffffff",
        gradient_bottom="#ecf1f7",
        text="#0f172a",
        subtle="#66718a",
        panel="#ffffff",
        panel_border="#d8e0e9",
        accent="#2563eb",
        accent_pressed="#1d4ed8",
        neutral="#e6edf5",
        neutral_hover="#d9e4f0",
        neutral_pressed="#cbd6e3",
        slider_track="#dbe4ef",
        slider_fill="#2563eb",
        slider_handle="#0f172a",
        progress_bg="#dbe4ef",
        progress_chunk="#2563eb",
    ),
    "aurora": Theme(
        key="aurora",
        label="Aurora",
        background="#050b0b",
        gradient_top="#0a1413",
        gradient_bottom="#050b0b",
        text="#e8fff5",
        subtle="#9fc7b8",
        panel="#0a1615",
        panel_border="#122422",
        accent="#3de2b5",
        accent_pressed="#2bb891",
        neutral="#0d1c1a",
        neutral_hover="#112421",
        neutral_pressed="#0b1614",
        slider_track="#1c302c",
        slider_fill="#3de2b5",
        slider_handle="#e8fff5",
        progress_bg="#1c302c",
        progress_chunk="#3de2b5",
    ),
    "berry": Theme(
        key="berry",
        label="Berry",
        background="#0c0712",
        gradient_top="#150a1f",
        gradient_bottom="#0c0712",
        text="#fff2ff",
        subtle="#c4a2cc",
        panel="#170d22",
        panel_border="#241532",
        accent="#e052bd",
        accent_pressed="#c43fa1",
        neutral="#1d1028",
        neutral_hover="#241734",
        neutral_pressed="#150d1f",
        slider_track="#2e1b3f",
        slider_fill="#e052bd",
        slider_handle="#fff2ff",
        progress_bg="#2e1b3f",
        progress_chunk="#e052bd",
    ),
    "neon": Theme(
        key="neon",
        label="Neon",
        background="#05060f",
        gradient_top="#0a0c1c",
        gradient_bottom="#05060f",
        text="#e8f0ff",
        subtle="#9aa7c7",
        panel="#0c1020",
        panel_border="#161a2e",
        accent="#7efc5a",
        accent_pressed="#5ed339",
        neutral="#12162a",
        neutral_hover="#161c34",
        neutral_pressed="#0e1224",
        slider_track="#222a40",
        slider_fill="#7efc5a",
        slider_handle="#e8f0ff",
        progress_bg="#222a40",
        progress_chunk="#7efc5a",
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
