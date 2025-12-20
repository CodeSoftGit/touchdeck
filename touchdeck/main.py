from __future__ import annotations

import asyncio
import sys

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication

from qasync import QEventLoop

from touchdeck.settings import load_settings
from touchdeck.themes import build_qss, get_theme
from touchdeck.ui.window import DeckWindow


def main() -> None:
    settings = load_settings()
    theme = get_theme(settings.theme)

    app = QApplication(sys.argv)
    app.setAttribute(Qt.AA_SynthesizeTouchForUnhandledMouseEvents, True)
    app.setStyleSheet(build_qss(theme))

    loop = QEventLoop(app)
    asyncio.set_event_loop(loop)

    w = DeckWindow(settings=settings)
    w.show()

    with loop:
        loop.run_forever()


if __name__ == "__main__":
    main()
