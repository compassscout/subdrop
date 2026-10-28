"""应用入口：加载主题、创建窗口。"""

from __future__ import annotations

import sys
from pathlib import Path

from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication

from .config import Settings


def asset_path(name: str) -> Path:
    if getattr(sys, "frozen", False):
        base = Path(sys.executable).resolve().parent
        candidates = [base / "assets" / name, base / "_internal" / "assets" / name]
        for candidate in candidates:
            if candidate.is_file():
                return candidate
        return candidates[0]
    return Path(__file__).resolve().parents[2] / "assets" / name


def _load_stylesheet(app: QApplication) -> None:
    qss = asset_path("style.qss")
    if qss.is_file():
        app.setStyleSheet(qss.read_text(encoding="utf-8"))


def _set_app_id() -> None:
    if sys.platform != "win32":
        return
    try:
        import ctypes

        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("SubDrop.Desktop.0.1")
    except Exception:  # noqa: BLE001
        pass


def run() -> int:
    _set_app_id()
    app = QApplication(sys.argv)
    app.setApplicationName("SubDrop")
    app.setApplicationDisplayName("SubDrop")
    app.setOrganizationName("SubDrop")
    _load_stylesheet(app)

    icon = asset_path("icon.ico")
    if not icon.is_file():
        icon = asset_path("icon.svg")
    if icon.is_file():
        app.setWindowIcon(QIcon(str(icon)))

    from .ui.main_window import MainWindow

    window = MainWindow(Settings.load())
    window.show()
    return app.exec()
