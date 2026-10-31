"""Start PrintEasy.   python -m printeasy   (add --tray to start hidden in the system tray)"""
from __future__ import annotations

import sys


def main() -> int:
    from PySide6.QtCore import QLockFile, QDir, Qt
    from PySide6.QtGui import QFont
    from PySide6.QtWidgets import QApplication, QMessageBox

    from . import APP_NAME
    from .ui import icons, theme
    from .ui.main_window import MainWindow

    QApplication.setHighDpiScaleFactorRoundingPolicy(Qt.HighDpiScaleFactorRoundingPolicy.PassThrough)
    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    app.setOrganizationName(APP_NAME)
    app.setDesktopFileName("printeasy")
    app.setWindowIcon(icons.app_icon())
    app.setQuitOnLastWindowClosed(False)
    app.setStyle("Fusion")                      # looks the same on Windows, Mac and Linux
    font = QFont(app.font())
    font.setPointSizeF(max(font.pointSizeF(), 11))
    app.setFont(font)
    app.setStyleSheet(theme.STYLE)

    # Only one copy at a time (stops two copies fighting over the default printer)
    lock = QLockFile(QDir.tempPath() + "/printeasy.lock")
    if not lock.tryLock(100):
        if "--tray" not in sys.argv:
            QMessageBox.information(None, APP_NAME, "PrintEasy is already open. Look for its icon near the clock.")
        return 0

    start_hidden = "--tray" in sys.argv
    win = MainWindow(start_hidden=start_hidden)
    if not start_hidden or win.tray is None:
        win.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
