from __future__ import annotations

import re
from functools import partial
from typing import Callable

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSlider,
    QSpinBox,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from touchdeck.settings import Settings, DEFAULT_PAGE_KEYS
from touchdeck.quick_actions import (
    DEFAULT_CUSTOM_ACTION_TIMEOUT_MS,
    CustomQuickAction,
    filter_quick_action_keys,
    generate_custom_action_key,
    ordered_quick_action_options,
)
from touchdeck.ui.widgets import Card
from touchdeck.themes import Theme, DEFAULT_THEME_KEY, get_theme, theme_options


PAGE_LABELS = {
    "music": "Music",
    "stats": "System stats",
    "clock": "Clock",
    "emoji": "Emoji",
    "speedtest": "Speed test",
    "settings": "Settings",
}

THEME_COLOR_FIELDS = [
    "background",
    "gradient_top",
    "gradient_bottom",
    "text",
    "subtle",
    "panel",
    "panel_border",
    "accent",
    "accent_pressed",
    "neutral",
    "neutral_hover",
    "neutral_pressed",
    "slider_track",
    "slider_fill",
    "slider_handle",
    "progress_bg",
    "progress_chunk",
]


def is_valid_color(value: str) -> bool:
    """Return True when the string looks like a hex color (#rrggbb)."""
    return bool(re.fullmatch(r"#([0-9a-fA-F]{6})", value.strip()))


class CustomActionRow(QWidget):
    def __init__(
        self,
        action: CustomQuickAction,
        *,
        theme: Theme,
        on_change=None,
        on_remove=None,
    ) -> None:
        super().__init__()
        self.key = action.key
        self._theme = theme
        self._on_change = on_change
        self._on_remove = on_remove

        self.title_input = QLineEdit(action.title)
        self.title_input.setPlaceholderText("Action title")
        self.title_input.textChanged.connect(self._emit_change)

        self.command_input = QLineEdit(action.command)
        self.command_input.setPlaceholderText("Command to run")
        self.command_input.textChanged.connect(self._emit_change)

        self.timeout_input = QSpinBox()
        self.timeout_input.setRange(1, 300)
        self.timeout_input.setSuffix(" s")
        self.timeout_input.setValue(max(1, int(action.timeout_ms / 1000)))
        self.timeout_input.valueChanged.connect(self._emit_change)

        remove_btn = QPushButton("Remove")
        remove_btn.setCursor(Qt.PointingHandCursor)
        remove_btn.clicked.connect(self._emit_remove)

        top = QHBoxLayout()
        top.setContentsMargins(0, 0, 0, 0)
        top.setSpacing(8)
        top.addWidget(self.title_input, 1)
        top.addWidget(remove_btn, 0)

        command_row = QHBoxLayout()
        command_row.setContentsMargins(0, 0, 0, 0)
        command_row.setSpacing(8)
        command_row.addWidget(self.command_input, 1)
        command_row.addWidget(self.timeout_input, 0)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(6)
        lay.addLayout(top)
        lay.addLayout(command_row)

        self._remove_btn = remove_btn
        self.apply_theme(theme)

    def to_action(self) -> CustomQuickAction:
        title = self.title_input.text().strip() or "Untitled action"
        command = self.command_input.text().strip() or "echo"
        timeout_ms = max(1, self.timeout_input.value()) * 1000
        return CustomQuickAction(
            key=self.key,
            title=title,
            command=command,
            timeout_ms=timeout_ms,
        )

    def apply_theme(self, theme: Theme) -> None:
        self._theme = theme
        input_style = f"""
            QLineEdit {{
                font-size: 16px;
                padding: 8px 10px;
                border-radius: 10px;
                background: {theme.neutral};
                color: {theme.text};
                border: 1px solid {theme.neutral_hover};
            }}
            QLineEdit:focus {{
                border: 1px solid {theme.accent};
            }}
            QSpinBox {{
                font-size: 16px;
                padding: 6px 10px;
                border-radius: 10px;
                background: {theme.neutral};
                color: {theme.text};
                border: 1px solid {theme.neutral_hover};
            }}
            QSpinBox::up-button, QSpinBox::down-button {{
                width: 0px;
                border: none;
            }}
        """
        self.title_input.setStyleSheet(input_style)
        self.command_input.setStyleSheet(input_style)
        self.timeout_input.setStyleSheet(input_style)
        self._remove_btn.setStyleSheet(
            f"""
            QPushButton {{
                padding: 8px 12px;
                border-radius: 10px;
                background: {theme.neutral};
                color: {theme.text};
                font-size: 14px;
                font-weight: 600;
            }}
            QPushButton:pressed {{
                background: {theme.neutral_pressed};
            }}
            """
        )

    def _emit_change(self, *_args) -> None:
        if callable(self._on_change):
            self._on_change()

    def _emit_remove(self) -> None:
        if callable(self._on_remove):
            self._on_remove(self.key)


class ToggleRow(QWidget):
    """Touch-friendly toggle button row with obvious on/off state."""

    def __init__(
        self,
        title: str,
        *,
        initial: bool = False,
        on_change: Callable[[bool], None] | None = None,
        parent: QWidget | None = None,
        theme: Theme | None = None,
    ) -> None:
        super().__init__(parent)
        self._title = title
        self._on_change = on_change
        self._theme = theme or get_theme(None)
        self._btn = QPushButton()
        self._btn.setCheckable(True)
        self._btn.setChecked(initial)
        self._btn.setCursor(Qt.PointingHandCursor)
        self._btn.clicked.connect(self._on_clicked)
        self._apply_theme()

        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.addWidget(self._btn)

        self._update_text()

    def _on_clicked(self) -> None:
        self._update_text()
        if self._on_change is not None:
            self._on_change(self._btn.isChecked())

    def _update_text(self) -> None:
        state = "On" if self._btn.isChecked() else "Off"
        self._btn.setText(f"{self._title} · {state}")

    def set_checked(self, checked: bool) -> None:
        self._btn.setChecked(checked)
        self._update_text()

    def is_checked(self) -> bool:
        return self._btn.isChecked()

    def apply_theme(self, theme: Theme) -> None:
        self._theme = theme
        self._apply_theme()

    def _apply_theme(self) -> None:
        self._btn.setStyleSheet(
            f"""
            QPushButton {{
                font-size: 18px;
                font-weight: 650;
                padding: 14px 16px;
                border-radius: 14px;
                text-align: left;
                background: {self._theme.neutral};
                color: {self._theme.text};
            }}
            QPushButton:checked {{
                background: {self._theme.accent};
                color: {self._theme.background};
            }}
            QPushButton:pressed {{
                background: {self._theme.accent_pressed};
            }}
            """
        )


class DragScrollArea(QScrollArea):
    """Scroll area that supports mouse/touch dragging to scroll."""

    def __init__(
        self, parent: QWidget | None = None, theme: Theme | None = None
    ) -> None:
        super().__init__(parent)
        self._theme = theme or get_theme(None)
        self._dragging = False
        self._last_y = 0.0
        self.setWidgetResizable(True)
        self.setFrameShape(QFrame.NoFrame)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self._apply_style()

    def mousePressEvent(self, ev) -> None:
        if ev.button() == Qt.LeftButton:
            self._dragging = True
            self._last_y = ev.position().y()
        super().mousePressEvent(ev)

    def mouseMoveEvent(self, ev) -> None:
        if self._dragging:
            dy = ev.position().y() - self._last_y
            self._last_y = ev.position().y()
            bar = self.verticalScrollBar()
            bar.setValue(bar.value() - int(dy))
        super().mouseMoveEvent(ev)

    def mouseReleaseEvent(self, ev) -> None:
        if ev.button() == Qt.LeftButton:
            self._dragging = False
        super().mouseReleaseEvent(ev)

    def apply_theme(self, theme: Theme) -> None:
        self._theme = theme
        self._apply_style()

    def _apply_style(self) -> None:
        self.setStyleSheet(
            f"""
            QScrollArea {{
                background: transparent;
            }}
            QScrollBar:vertical {{
                background: transparent;
                width: 12px;
                margin: 8px 4px 8px 0px;
            }}
            QScrollBar::handle:vertical {{
                background: {self._theme.neutral_hover};
                border-radius: 6px;
                min-height: 36px;
            }}
            QScrollBar::handle:vertical:pressed {{
                background: {self._theme.neutral_pressed};
            }}
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
                height: 0px;
            }}
            QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{
                background: transparent;
            }}
            """
        )


class ColorPickerDialog(QDialog):
    """Simple RGB/hex picker that stays within the TouchDeck UI."""

    def __init__(
        self, parent: QWidget | None, *, initial: str, ui_theme: Theme
    ) -> None:
        super().__init__(parent)
        self.setModal(True)
        self.setWindowTitle("Pick color")
        self.setMinimumWidth(420)
        self._ui_theme = ui_theme
        self._color = QColor(initial if is_valid_color(initial) else "#ffffff")
        self.result_hex: str | None = None

        self.setStyleSheet(
            f"""
            QDialog {{
                background: {ui_theme.panel};
                color: {ui_theme.text};
            }}
            QLabel {{
                color: {ui_theme.text};
            }}
            QLineEdit {{
                padding: 10px 12px;
                border-radius: 10px;
                background: {ui_theme.neutral};
                color: {ui_theme.text};
                border: 1px solid {ui_theme.neutral_hover};
                selection-background-color: {ui_theme.accent};
                selection-color: {ui_theme.background};
            }}
            QSlider::groove:horizontal {{
                height: 10px;
                border-radius: 5px;
                background: {ui_theme.slider_track};
            }}
            QSlider::handle:horizontal {{
                width: 22px;
                height: 22px;
                margin: -6px 0;
                border-radius: 11px;
                background: {ui_theme.slider_handle};
            }}
            QPushButton {{
                padding: 10px 12px;
                border-radius: 10px;
                background: {ui_theme.neutral};
                color: {ui_theme.text};
            }}
            QPushButton:pressed {{
                background: {ui_theme.neutral_pressed};
            }}
            """
        )

        main = QVBoxLayout(self)
        main.setContentsMargins(16, 16, 16, 16)
        main.setSpacing(10)

        self.preview = QLabel()
        self.preview.setFixedHeight(44)
        self.preview.setStyleSheet(
            f"border-radius: 12px; border: 1px solid {ui_theme.panel_border};"
        )

        self.hex_input = QLineEdit(self._color.name(QColor.HexRgb))
        self.hex_input.textChanged.connect(self._on_hex_changed)

        sliders = QVBoxLayout()
        self._slider_rows = []
        for channel, getter in (
            ("R", QColor.red),
            ("G", QColor.green),
            ("B", QColor.blue),
        ):
            row = QHBoxLayout()
            row.setSpacing(8)
            lbl = QLabel(channel)
            lbl.setFixedWidth(18)
            slider = QSlider(Qt.Horizontal)
            slider.setRange(0, 255)
            slider.valueChanged.connect(self._on_slider_changed)
            value_lbl = QLabel("0")
            value_lbl.setFixedWidth(32)
            row.addWidget(lbl)
            row.addWidget(slider, 1)
            row.addWidget(value_lbl)
            sliders.addLayout(row)
            self._slider_rows.append((slider, value_lbl, getter))

        buttons = QDialogButtonBox(QDialogButtonBox.Cancel | QDialogButtonBox.Save)
        if buttons.button(QDialogButtonBox.Save):
            buttons.button(QDialogButtonBox.Save).setText("Use color")
            buttons.button(QDialogButtonBox.Save).setCursor(Qt.PointingHandCursor)
        if buttons.button(QDialogButtonBox.Cancel):
            buttons.button(QDialogButtonBox.Cancel).setCursor(Qt.PointingHandCursor)
        buttons.accepted.connect(self._accept)
        buttons.rejected.connect(self.reject)

        main.addWidget(QLabel("Adjust color"), 0)
        main.addWidget(self.preview)
        main.addWidget(QLabel("Hex (e.g. #112233)"))
        main.addWidget(self.hex_input)
        main.addLayout(sliders)
        main.addStretch(1)
        main.addWidget(buttons)

        self._sync_from_color()

    def _sync_from_color(self) -> None:
        for slider, value_lbl, getter in self._slider_rows:
            slider.blockSignals(True)
            slider.setValue(getter(self._color))
            slider.blockSignals(False)
            value_lbl.setText(str(getter(self._color)))
        hex_val = self._color.name(QColor.HexRgb)
        if self.hex_input.text() != hex_val:
            self.hex_input.blockSignals(True)
            self.hex_input.setText(hex_val)
            self.hex_input.blockSignals(False)
        self.preview.setStyleSheet(
            f"border-radius: 12px; border: 1px solid {self._ui_theme.panel_border}; background: {hex_val};"
        )

    def _on_hex_changed(self, text: str) -> None:
        if is_valid_color(text):
            self._color = QColor(text)
            self._sync_from_color()
        else:
            # Indicate invalid state
            self.preview.setStyleSheet(
                f"border-radius: 12px; border: 1px solid {self._ui_theme.accent}; background: {self._ui_theme.neutral_pressed};"
            )

    def _on_slider_changed(self, _value: int) -> None:
        r = self._slider_rows[0][0].value()
        g = self._slider_rows[1][0].value()
        b = self._slider_rows[2][0].value()
        self._color = QColor(r, g, b)
        self._sync_from_color()

    def _accept(self) -> None:
        hex_val = self._color.name(QColor.HexRgb)
        self.result_hex = hex_val
        super().accept()


class ThemeCreatorDialog(QDialog):
    """Lightweight editor to build a custom theme and persist it to disk."""

    def __init__(
        self, parent: QWidget | None, *, base_theme: Theme, ui_theme: Theme
    ) -> None:
        super().__init__(parent)
        self.setModal(True)
        self.setWindowTitle("Create theme")
        self.setMinimumWidth(520)
        self.result_theme: Theme | None = None
        self._ui_theme = ui_theme
        self._color_inputs: dict[str, QLineEdit] = {}
        self._color_buttons: dict[str, QPushButton] = {}
        default_key = self._slugify_key(f"{base_theme.key}_custom")

        self.setStyleSheet(
            f"""
            QDialog {{
                background: {ui_theme.panel};
                color: {ui_theme.text};
            }}
            QLabel {{
                color: {ui_theme.text};
            }}
            QLineEdit {{
                padding: 10px 12px;
                border-radius: 10px;
                background: {ui_theme.neutral};
                color: {ui_theme.text};
                border: 1px solid {ui_theme.neutral_hover};
                selection-background-color: {ui_theme.accent};
                selection-color: {ui_theme.background};
            }}
            QPushButton {{
                padding: 10px 12px;
                border-radius: 10px;
                background: {ui_theme.neutral};
                color: {ui_theme.text};
            }}
            QPushButton:pressed {{
                background: {ui_theme.neutral_pressed};
            }}
            """
        )

        main = QVBoxLayout(self)
        main.setContentsMargins(18, 18, 18, 18)
        main.setSpacing(12)

        title = QLabel("Build a custom color theme")
        title.setStyleSheet("font-size: 22px; font-weight: 750;")
        info = QLabel(
            "Start from the current theme, tweak colors, and save. Themes are stored in ~/.config/touchdeck/themes.json."
        )
        info.setWordWrap(True)
        info.setObjectName("Subtle")

        meta_form = QFormLayout()
        meta_form.setSpacing(10)
        self.label_input = QLineEdit(f"{base_theme.label} Custom")
        self.key_input = QLineEdit(default_key or base_theme.key)
        meta_form.addRow("Theme name", self.label_input)
        meta_form.addRow("Theme id", self.key_input)

        colors_title = QLabel("Colors")
        colors_title.setStyleSheet(
            "font-size: 16px; font-weight: 700; padding-top: 4px;"
        )

        colors = QGridLayout()
        colors.setHorizontalSpacing(10)
        colors.setVerticalSpacing(8)
        colors.setColumnStretch(1, 1)
        for idx, field in enumerate(THEME_COLOR_FIELDS):
            label = QLabel(field.replace("_", " ").title())
            input_box = QLineEdit(getattr(base_theme, field))
            pick = QPushButton("Pick")
            pick.setCursor(Qt.PointingHandCursor)
            self._color_inputs[field] = input_box
            self._color_buttons[field] = pick
            pick.clicked.connect(partial(self._pick_color, field))
            input_box.textChanged.connect(partial(self._update_color_button, field))

            row = idx
            colors.addWidget(label, row, 0)
            colors.addWidget(input_box, row, 1)
            colors.addWidget(pick, row, 2)
            self._update_color_button(field, input_box.text())

        buttons = QDialogButtonBox(QDialogButtonBox.Cancel | QDialogButtonBox.Save)
        btn_save = buttons.button(QDialogButtonBox.Save)
        if btn_save:
            btn_save.setText("Save theme")
            btn_save.setCursor(Qt.PointingHandCursor)
        btn_cancel = buttons.button(QDialogButtonBox.Cancel)
        if btn_cancel:
            btn_cancel.setCursor(Qt.PointingHandCursor)
        buttons.accepted.connect(self._on_accept)
        buttons.rejected.connect(self.reject)

        main.addWidget(title)
        main.addWidget(info)
        main.addLayout(meta_form)
        main.addWidget(colors_title)
        main.addLayout(colors)
        main.addStretch(1)
        main.addWidget(buttons)

    def _slugify_key(self, raw: str) -> str:
        cleaned = re.sub(r"[^a-zA-Z0-9_-]+", "-", raw.strip().lower())
        cleaned = re.sub(r"-{2,}", "-", cleaned).strip("-")
        return cleaned[:48]

    def _pick_color(self, field: str) -> None:
        current = self._color_inputs[field].text()
        dlg = ColorPickerDialog(self, initial=current, ui_theme=self._ui_theme)
        if dlg.exec() == QDialog.Accepted and dlg.result_hex:
            self._color_inputs[field].setText(dlg.result_hex)

    def _update_color_button(self, field: str, value: str) -> None:
        btn = self._color_buttons.get(field)
        if not btn:
            return
        if is_valid_color(value):
            btn.setStyleSheet(
                f"background: {value}; color: {self._ui_theme.background}; border-radius: 10px;"
            )
        else:
            btn.setStyleSheet(
                f"background: {self._ui_theme.neutral_pressed}; color: {self._ui_theme.text}; border-radius: 10px;"
            )

    def _on_accept(self) -> None:
        label = self.label_input.text().strip()
        key_input = self.key_input.text().strip()
        key = self._slugify_key(key_input or label or "custom")
        if not key:
            QMessageBox.warning(
                self,
                "Theme id required",
                "Enter a theme id using letters, numbers, dashes, or underscores.",
            )
            return

        colors: dict[str, str] = {}
        for field, line in self._color_inputs.items():
            val = line.text().strip()
            if not is_valid_color(val):
                QMessageBox.warning(
                    self,
                    "Invalid color",
                    f"{field.replace('_', ' ').title()} must be a hex color like #112233.",
                )
                return
            colors[field] = val

        label = label or key.replace("-", " ").replace("_", " ").title()
        self.result_theme = Theme(key=key, label=label, **colors)
        super().accept()


class SettingsPage(QWidget):
    def __init__(
        self,
        settings: Settings,
        on_change,
        on_exit,
        on_reset,
        parent: QWidget | None = None,
        theme: Theme | None = None,
    ) -> None:
        super().__init__(parent)
        self._on_change = on_change
        self._on_exit = on_exit
        self._on_reset = on_reset
        self._settings = settings
        self._theme = theme or get_theme(settings.theme)
        self._syncing = True  # suppress change events until initial wiring completes
        self.card = Card(theme=self._theme)

        title = QLabel("Settings")
        title.setStyleSheet("font-size: 28px; font-weight: 700;")

        # Toggles sized for touch
        self.toggle_gpu = ToggleRow(
            "Enable GPU stats",
            initial=settings.enable_gpu_stats,
            on_change=self._emit_change,
            theme=self._theme,
        )
        self.toggle_clock = ToggleRow(
            "24-hour clock",
            initial=settings.clock_24h,
            on_change=self._emit_change,
            theme=self._theme,
        )
        self.toggle_seconds = ToggleRow(
            "Show seconds on clock",
            initial=settings.show_clock_seconds,
            on_change=self._emit_change,
            theme=self._theme,
        )
        self.toggle_demo = ToggleRow(
            "Demo mode (windowed)",
            initial=settings.demo_mode,
            on_change=self._emit_change,
            theme=self._theme,
        )

        # Page selector
        self.page_checks: list[tuple[str, QCheckBox]] = []
        page_grid = QGridLayout()
        page_grid.setContentsMargins(0, 0, 0, 0)
        page_grid.setSpacing(8)
        for idx, key in enumerate(DEFAULT_PAGE_KEYS):
            label = PAGE_LABELS.get(key, key.title())
            cb = QCheckBox(label)
            cb.stateChanged.connect(self._emit_change)
            if key == "settings":
                cb.setChecked(True)
                cb.setEnabled(False)
            self._style_checkbox(cb)
            row, col = divmod(idx, 2)
            page_grid.addWidget(cb, row, col)
            self.page_checks.append((key, cb))

        # Quick actions
        self.quick_action_checks: list[tuple[str, QCheckBox]] = []
        self._quick_actions_grid = QGridLayout()
        self._quick_actions_grid.setContentsMargins(0, 0, 0, 0)
        self._quick_actions_grid.setSpacing(8)
        self._custom_action_rows: list[CustomActionRow] = []
        self._custom_actions_wrap = QVBoxLayout()
        self._custom_actions_wrap.setContentsMargins(0, 0, 0, 0)
        self._custom_actions_wrap.setSpacing(10)
        self._custom_actions_panel = self._build_custom_actions_panel()

        # Theme selector
        theme_row = QHBoxLayout()
        theme_row.setContentsMargins(0, 0, 0, 0)
        theme_row.addWidget(QLabel("Color theme"), 1)
        self.theme_picker = QComboBox()
        for opt in theme_options():
            self.theme_picker.addItem(opt.label, opt.key)
        self.theme_picker.currentIndexChanged.connect(self._emit_change)
        theme_row.addWidget(self.theme_picker, 0)

        # Brightness control
        bright_row = QHBoxLayout()
        bright_row.setContentsMargins(0, 0, 0, 0)
        bright_row.addWidget(QLabel("Brightness"), 1)
        self.brightness_value = QLabel("70%")
        self.brightness_value.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        self.brightness_value.setObjectName("Subtle")
        bright_row.addWidget(self.brightness_value, 0)

        self.brightness = QSlider(Qt.Horizontal)
        self.brightness.setRange(0, 100)
        self.brightness.valueChanged.connect(self._on_brightness_change)

        # Poll intervals
        self.music_poll_value = QLabel("0 ms")
        self.music_poll_value.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        self.music_poll_value.setObjectName("Subtle")
        music_row = QHBoxLayout()
        music_row.setContentsMargins(0, 0, 0, 0)
        music_row.addWidget(QLabel("Music refresh"), 1)
        music_row.addWidget(self.music_poll_value, 0)

        self.music_poll = QSlider(Qt.Horizontal)
        self.music_poll.setRange(250, 3000)
        self.music_poll.valueChanged.connect(self._on_poll_change)

        self.stats_poll_value = QLabel("0 ms")
        self.stats_poll_value.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        self.stats_poll_value.setObjectName("Subtle")
        stats_row = QHBoxLayout()
        stats_row.setContentsMargins(0, 0, 0, 0)
        stats_row.addWidget(QLabel("Stats refresh"), 1)
        stats_row.addWidget(self.stats_poll_value, 0)

        self.stats_poll = QSlider(Qt.Horizontal)
        self.stats_poll.setRange(500, 5000)
        self.stats_poll.valueChanged.connect(self._on_poll_change)

        # Submenu navigation
        self._sections = QStackedWidget()
        self._nav_buttons: list[QPushButton] = []
        nav_row = QHBoxLayout()
        nav_row.setContentsMargins(0, 0, 0, 0)
        nav_row.setSpacing(8)

        sections = [
            ("General", self._build_general_section()),
            (
                "Pages & Actions",
                self._build_pages_actions_section(page_grid),
            ),
            ("Display", self._build_display_section(theme_row, bright_row)),
            ("Refresh", self._build_refresh_section(music_row, stats_row)),
        ]

        for idx, (label, widget) in enumerate(sections):
            self._sections.addWidget(widget)
            btn = QPushButton(label)
            btn.setCheckable(True)
            btn.setCursor(Qt.PointingHandCursor)
            btn.clicked.connect(partial(self._on_nav_clicked, idx))
            self._nav_buttons.append(btn)
            nav_row.addWidget(btn)
        nav_row.addStretch(1)

        self.card.body.addWidget(title)
        self.card.body.addSpacing(10)
        self.card.body.addLayout(nav_row)
        self.card.body.addWidget(self._sections)
        self.card.body.addSpacing(14)
        self.exit_btn = QPushButton("Exit TouchDeck")
        self.exit_btn.clicked.connect(self._on_exit_clicked)
        self._style_exit_button(self.exit_btn)
        self.reset_btn = QPushButton("Reset app data and restart")
        self.reset_btn.clicked.connect(self._on_reset_clicked)
        self._style_reset_button(self.reset_btn)
        self.card.body.addWidget(self.exit_btn)
        self.card.body.addWidget(self.reset_btn)

        content = QWidget()
        content_lay = QVBoxLayout(content)
        content_lay.setContentsMargins(26, 26, 26, 26)
        content_lay.addWidget(self.card)

        scroll = DragScrollArea(theme=self._theme)
        scroll.setWidget(content)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.addWidget(scroll)

        self._set_section(0)
        self.apply_settings(settings)

    def apply_settings(self, settings: Settings) -> None:
        self._syncing = True
        self._settings = settings
        self.toggle_gpu.set_checked(settings.enable_gpu_stats)
        self.toggle_clock.set_checked(settings.clock_24h)
        self.toggle_seconds.set_checked(settings.show_clock_seconds)
        self.toggle_demo.set_checked(settings.demo_mode)
        selected_pages = set(settings.enabled_pages)
        for key, cb in self.page_checks:
            cb.blockSignals(True)
            cb.setChecked(key in selected_pages or key == "settings")
            cb.blockSignals(False)
        self._set_theme_picker(settings.theme)
        self.brightness.blockSignals(True)
        self.brightness.setValue(settings.ui_opacity_percent)
        self.brightness.blockSignals(False)
        self._apply_custom_actions(settings.custom_actions)
        selected_actions = set(settings.quick_actions)
        for key, cb in self.quick_action_checks:
            cb.blockSignals(True)
            cb.setChecked(key in selected_actions)
            cb.blockSignals(False)
        self._on_brightness_change(settings.ui_opacity_percent)
        self.music_poll.blockSignals(True)
        self.music_poll.setValue(settings.music_poll_ms)
        self.music_poll.blockSignals(False)
        self.stats_poll.blockSignals(True)
        self.stats_poll.setValue(settings.stats_poll_ms)
        self.stats_poll.blockSignals(False)
        self._update_poll_labels(settings.music_poll_ms, settings.stats_poll_ms)
        self._syncing = False

    def _apply_custom_actions(self, actions: list[CustomQuickAction]) -> None:
        incoming_keys = [action.key for action in actions]
        current_keys = [row.key for row in self._custom_action_rows]
        if incoming_keys != current_keys:
            self._sync_custom_actions(actions)
            self._rebuild_quick_actions_grid(actions)
            return

        for row, action in zip(self._custom_action_rows, actions):
            self._update_custom_action_row(row, action)

        self._refresh_quick_action_labels(actions)

    def _update_custom_action_row(
        self, row: CustomActionRow, action: CustomQuickAction
    ) -> None:
        if row.title_input.hasFocus() or row.command_input.hasFocus():
            return

        row.title_input.blockSignals(True)
        row.command_input.blockSignals(True)
        if row.title_input.text() != action.title:
            row.title_input.setText(action.title)
        if row.command_input.text() != action.command:
            row.command_input.setText(action.command)
        row.title_input.blockSignals(False)
        row.command_input.blockSignals(False)

        if row.timeout_input.hasFocus():
            return

        row.timeout_input.blockSignals(True)
        timeout_s = max(1, int(action.timeout_ms / 1000))
        if row.timeout_input.value() != timeout_s:
            row.timeout_input.setValue(timeout_s)
        row.timeout_input.blockSignals(False)

    def _refresh_quick_action_labels(
        self, actions: list[CustomQuickAction]
    ) -> None:
        if not self.quick_action_checks:
            return
        lookup = {action.key: action for action in actions}
        for key, cb in self.quick_action_checks:
            action = lookup.get(key)
            if action is None:
                continue
            if cb.text() != action.title:
                cb.setText(action.title)
            cb.setToolTip(action.command)

    def _on_brightness_change(self, value: int) -> None:
        self.brightness_value.setText(f"{value}%")
        self._emit_change()

    def _emit_change(self, *_args) -> None:
        if self._syncing:
            return
        new_settings = Settings(
            enable_gpu_stats=self.toggle_gpu.is_checked(),
            clock_24h=self.toggle_clock.is_checked(),
            show_clock_seconds=self.toggle_seconds.is_checked(),
            music_poll_ms=self.music_poll.value(),
            stats_poll_ms=self.stats_poll.value(),
            ui_opacity_percent=self.brightness.value(),
            theme=self.theme_picker.currentData() or DEFAULT_THEME_KEY,
            quick_actions=self._selected_quick_actions(),
            preferred_display=self._settings.preferred_display,
            demo_mode=self.toggle_demo.is_checked(),
            display_selected=self._settings.display_selected,
            onboarding_completed=self._settings.onboarding_completed,
            enabled_pages=self._selected_pages(),
            custom_actions=self._collect_custom_actions(),
        )
        if callable(self._on_change):
            self._on_change(new_settings)

    def _on_poll_change(self, value: int) -> None:
        self._update_poll_labels(self.music_poll.value(), self.stats_poll.value())
        self._emit_change()

    def _update_poll_labels(self, music_ms: int, stats_ms: int) -> None:
        self.music_poll_value.setText(f"{music_ms} ms")
        self.stats_poll_value.setText(f"{stats_ms} ms")

    def _set_theme_picker(self, key: str) -> None:
        idx = self.theme_picker.findData(key)
        if idx < 0:
            idx = self.theme_picker.findData(DEFAULT_THEME_KEY)
        if idx >= 0:
            self.theme_picker.blockSignals(True)
            self.theme_picker.setCurrentIndex(idx)
            self.theme_picker.blockSignals(False)

    def apply_theme(self, theme: Theme) -> None:
        self._theme = theme
        self.card.apply_theme(theme)
        self.toggle_gpu.apply_theme(theme)
        self.toggle_clock.apply_theme(theme)
        self.toggle_seconds.apply_theme(theme)
        self.toggle_demo.apply_theme(theme)
        self._style_sliders()
        self._style_theme_picker()
        self._style_nav_buttons()
        for _, cb in self.quick_action_checks:
            self._style_checkbox(cb)
        for _, cb in self.page_checks:
            self._style_checkbox(cb)
        for row in self._custom_action_rows:
            row.apply_theme(theme)
        self._style_add_custom_action_button()
        self._style_exit_button(self.exit_btn)
        self._style_reset_button(self.reset_btn)

    def _style_sliders(self) -> None:
        # Make sliders chunkier for touch
        slider_style = f"""
            QSlider::groove:horizontal {{
                height: 12px;
                border-radius: 6px;
            }}
            QSlider::handle:horizontal {{
                width: 26px;
                height: 26px;
                margin: -7px 0;
                border-radius: 13px;
                background: {self._theme.slider_handle};
            }}
        """
        for sl in (self.brightness, self.music_poll, self.stats_poll):
            sl.setStyleSheet(slider_style)

    def _style_theme_picker(self) -> None:
        self.theme_picker.setStyleSheet(
            f"""
            QComboBox {{
                font-size: 18px;
                padding: 12px 14px;
                border-radius: 12px;
                background: {self._theme.neutral};
                color: {self._theme.text};
            }}
            QComboBox::drop-down {{
                width: 26px;
            }}
            QComboBox QAbstractItemView {{
                background: {self._theme.panel};
                color: {self._theme.text};
                selection-background-color: {self._theme.accent};
                selection-color: {self._theme.background};
            }}
            """
        )

    def _selected_quick_actions(self) -> list[str]:
        chosen = [key for key, cb in self.quick_action_checks if cb.isChecked()]
        return filter_quick_action_keys(chosen, self._collect_custom_actions())

    def _collect_custom_actions(self) -> list[CustomQuickAction]:
        actions: list[CustomQuickAction] = []
        for row in self._custom_action_rows:
            actions.append(row.to_action())
        return actions

    def _selected_pages(self) -> list[str]:
        chosen = [
            key for key, cb in self.page_checks if cb.isChecked() or key == "settings"
        ]
        # Maintain canonical ordering
        ordered = [p for p in DEFAULT_PAGE_KEYS if p in chosen]
        for p in chosen:
            if p not in ordered:
                ordered.append(p)
        if "settings" not in ordered:
            ordered.append("settings")
        return ordered

    def _style_checkbox(self, cb: QCheckBox) -> None:
        cb.setStyleSheet(
            f"""
            QCheckBox {{
                font-size: 17px;
                padding: 10px 4px;
                color: {self._theme.text};
            }}
            QCheckBox::indicator {{
                width: 26px;
                height: 26px;
            }}
            QCheckBox::indicator:unchecked {{
                border-radius: 6px;
                border: 2px solid {self._theme.neutral_hover};
                background: {self._theme.neutral};
            }}
            QCheckBox::indicator:checked {{
                border-radius: 6px;
                background: {self._theme.accent};
                border: 2px solid {self._theme.accent};
            }}
            """
        )

    def _style_nav_buttons(self) -> None:
        for btn in self._nav_buttons:
            btn.setStyleSheet(
                f"""
                QPushButton {{
                    padding: 10px 14px;
                    border-radius: 12px;
                    background: {self._theme.neutral};
                    color: {self._theme.text};
                    font-size: 16px;
                    font-weight: 700;
                }}
                QPushButton:checked {{
                    background: {self._theme.accent};
                    color: {self._theme.background};
                }}
                QPushButton:pressed {{
                    background: {self._theme.neutral_pressed};
                }}
                QPushButton:checked:pressed {{
                    background: {self._theme.accent_pressed};
                }}
                """
            )

    def _style_exit_button(self, btn: QPushButton) -> None:
        btn.setCursor(Qt.PointingHandCursor)
        btn.setStyleSheet(
            f"""
            QPushButton {{
                padding: 12px 16px;
                border-radius: 14px;
                background: {self._theme.accent};
                color: {self._theme.background};
                font-size: 18px;
                font-weight: 750;
            }}
            QPushButton:pressed {{
                background: {self._theme.accent_pressed};
            }}
            """
        )

    def _style_reset_button(self, btn: QPushButton) -> None:
        btn.setCursor(Qt.PointingHandCursor)
        btn.setStyleSheet(
            f"""
            QPushButton {{
                padding: 12px 16px;
                border-radius: 14px;
                background: {self._theme.neutral};
                color: {self._theme.text};
                font-size: 16px;
                font-weight: 700;
            }}
            QPushButton:pressed {{
                background: {self._theme.neutral_pressed};
            }}
            """
        )

    def _style_add_custom_action_button(self) -> None:
        btn = getattr(self, "_add_custom_action_btn", None)
        if btn is None:
            return
        btn.setStyleSheet(
            f"""
            QPushButton {{
                padding: 8px 12px;
                border-radius: 10px;
                background: {self._theme.neutral};
                color: {self._theme.text};
                font-size: 14px;
                font-weight: 650;
            }}
            QPushButton:pressed {{
                background: {self._theme.neutral_pressed};
            }}
            """
        )

    def _on_exit_clicked(self) -> None:
        if callable(self._on_exit):
            self._on_exit()

    def _on_reset_clicked(self) -> None:
        if callable(self._on_reset):
            self._on_reset()

    def _on_nav_clicked(self, idx: int) -> None:
        self._set_section(idx)

    def _set_section(self, idx: int) -> None:
        idx = max(0, min(self._sections.count() - 1, idx))
        self._sections.setCurrentIndex(idx)
        for i, btn in enumerate(self._nav_buttons):
            btn.blockSignals(True)
            btn.setChecked(i == idx)
            btn.blockSignals(False)
        self._style_nav_buttons()

    def _section_title(self, text: str) -> QLabel:
        lbl = QLabel(text)
        lbl.setObjectName("Subtle")
        lbl.setStyleSheet("font-size: 16px; font-weight: 650; padding-top: 4px;")
        return lbl

    def _build_general_section(self) -> QWidget:
        section = QWidget()
        lay = QVBoxLayout(section)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(10)
        lay.addWidget(self._section_title("General"))
        lay.addWidget(self.toggle_gpu)
        lay.addWidget(self.toggle_clock)
        lay.addWidget(self.toggle_seconds)
        lay.addWidget(self.toggle_demo)
        lay.addStretch(1)
        return section

    def _build_pages_actions_section(self, page_grid: QGridLayout) -> QWidget:
        section = QWidget()
        lay = QVBoxLayout(section)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(10)
        lay.addWidget(self._section_title("Pages"))
        lay.addLayout(page_grid)
        lay.addSpacing(8)
        lay.addWidget(self._section_title("Quick actions"))
        lay.addLayout(self._quick_actions_grid)
        lay.addSpacing(8)
        lay.addWidget(self._section_title("Custom actions"))
        lay.addWidget(self._custom_actions_panel)
        lay.addStretch(1)
        return section

    def _build_custom_actions_panel(self) -> QWidget:
        panel = QWidget()
        lay = QVBoxLayout(panel)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(8)

        info = QLabel(
            "Use {title}, {artist}, {album}, {status}, {position_ms}, {length_ms}, "
            "{track_id}, {bus_name}, {position_mmss}, {length_mmss}"
        )
        info.setObjectName("Subtle")
        info.setWordWrap(True)

        self._add_custom_action_btn = QPushButton("Add custom action")
        self._add_custom_action_btn.setCursor(Qt.PointingHandCursor)
        self._add_custom_action_btn.clicked.connect(self._add_custom_action)

        lay.addLayout(self._custom_actions_wrap)
        lay.addWidget(info)
        lay.addWidget(self._add_custom_action_btn, alignment=Qt.AlignLeft)
        return panel

    def _sync_custom_actions(self, actions: list[CustomQuickAction]) -> None:
        while self._custom_actions_wrap.count():
            item = self._custom_actions_wrap.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()
        self._custom_action_rows.clear()
        for action in actions:
            row = CustomActionRow(
                action,
                theme=self._theme,
                on_change=self._emit_change,
                on_remove=self._remove_custom_action,
            )
            self._custom_actions_wrap.addWidget(row)
            self._custom_action_rows.append(row)

    def _rebuild_quick_actions_grid(
        self, custom_actions: list[CustomQuickAction]
    ) -> None:
        while self._quick_actions_grid.count():
            item = self._quick_actions_grid.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()
        self.quick_action_checks.clear()
        options = ordered_quick_action_options(custom_actions)
        for idx, action in enumerate(options):
            cb = QCheckBox(action.label)
            cb.setToolTip(action.description)
            cb.stateChanged.connect(self._emit_change)
            self._style_checkbox(cb)
            row, col = divmod(idx, 2)
            self._quick_actions_grid.addWidget(cb, row, col)
            self.quick_action_checks.append((action.key, cb))

    def _add_custom_action(self) -> None:
        existing = {key for key, _ in self.quick_action_checks}
        title = "New action"
        key = generate_custom_action_key(title, existing)
        action = CustomQuickAction(
            key=key,
            title=title,
            command='echo "{title} - {artist}"',
            timeout_ms=DEFAULT_CUSTOM_ACTION_TIMEOUT_MS,
        )
        row = CustomActionRow(
            action,
            theme=self._theme,
            on_change=self._emit_change,
            on_remove=self._remove_custom_action,
        )
        self._custom_actions_wrap.addWidget(row)
        self._custom_action_rows.append(row)
        self._emit_change()

    def _remove_custom_action(self, key: str) -> None:
        row = next((r for r in self._custom_action_rows if r.key == key), None)
        if row is None:
            return
        self._custom_actions_wrap.removeWidget(row)
        row.deleteLater()
        self._custom_action_rows = [r for r in self._custom_action_rows if r.key != key]
        self._emit_change()

    def _build_display_section(
        self, theme_row: QHBoxLayout, bright_row: QHBoxLayout
    ) -> QWidget:
        section = QWidget()
        lay = QVBoxLayout(section)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(12)
        lay.addWidget(self._section_title("Appearance"))
        lay.addLayout(theme_row)
        lay.addSpacing(4)
        lay.addWidget(self._section_title("Brightness"))
        lay.addLayout(bright_row)
        lay.addWidget(self.brightness)
        lay.addStretch(1)
        return section

    def _build_refresh_section(
        self, music_row: QHBoxLayout, stats_row: QHBoxLayout
    ) -> QWidget:
        section = QWidget()
        lay = QVBoxLayout(section)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(12)
        lay.addWidget(self._section_title("Refresh"))
        lay.addLayout(music_row)
        lay.addWidget(self.music_poll)
        lay.addLayout(stats_row)
        lay.addWidget(self.stats_poll)
        lay.addStretch(1)
        return section
