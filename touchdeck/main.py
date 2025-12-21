from __future__ import annotations

import asyncio
import sys
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication, QDialog

from qasync import QEventLoop

from touchdeck.settings import load_settings, save_settings
from touchdeck.themes import build_qss, get_theme
from touchdeck.ui.window import DeckWindow
from touchdeck.ui.dialogs import DisplayChoiceDialog


def _load_app_icon() -> QIcon:
    return QIcon(str(Path(__file__).resolve().parent / "logo" / "square.svg"))


def _load_full_logo_icon() -> QIcon:
    return QIcon(str(Path(__file__).resolve().parent / "images" / "logo.svg"))


def main() -> None:
    app = QApplication(sys.argv)
    app.setAttribute(Qt.AA_SynthesizeTouchForUnhandledMouseEvents, True)
    app_icon = _load_app_icon()
    full_logo_icon = _load_full_logo_icon()
    if not app_icon.isNull():
        app.setWindowIcon(app_icon)

    settings = load_settings()
    theme = get_theme(settings.theme)
    app.setStyleSheet(build_qss(theme))

    loop = QEventLoop(app)
    asyncio.set_event_loop(loop)

    if not settings.display_selected:
        dlg = DisplayChoiceDialog(
            app.screens(),
            current_display=settings.preferred_display,
            demo_mode=settings.demo_mode,
        )
        if dlg.exec() == QDialog.Accepted:
            settings.preferred_display = dlg.selected_display()
            settings.demo_mode = dlg.is_demo_mode()
            settings.display_selected = True
            save_settings(settings)

    w = DeckWindow(
        settings=settings, logo_icon=app_icon, startup_logo_icon=full_logo_icon
    )
    if not app_icon.isNull():
        w.setWindowIcon(app_icon)
    if settings.demo_mode:
        w.show()
    else:
        w.showFullScreen()

    with loop:
        loop.run_forever()


if __name__ == "__main__":
    main()
