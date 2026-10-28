"""通用小部件：拖拽区、卡片、标题。"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor, QDragEnterEvent, QDropEvent, QMouseEvent, QPainter, QPen
from PySide6.QtWidgets import QFileDialog, QFrame, QLabel, QVBoxLayout, QWidget

from ..core.media import SUPPORTED_EXTENSIONS, format_size


def page_title(text: str) -> QLabel:
    label = QLabel(text)
    label.setObjectName("pageTitle")
    return label


def subtitle(text: str) -> QLabel:
    label = QLabel(text)
    label.setObjectName("pageSubtitle")
    label.setWordWrap(True)
    return label


def muted(text: str = "") -> QLabel:
    label = QLabel(text)
    label.setObjectName("muted")
    label.setWordWrap(True)
    return label


class Card(QFrame):
    def __init__(self, parent: QWidget | None = None, spacing: int = 12) -> None:
        super().__init__(parent)
        self.setObjectName("card")
        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(18, 16, 18, 16)
        self.layout.setSpacing(spacing)


class DropArea(QFrame):
    """整个窗口里最显眼的那个框：拖进来，或者点一下选文件。"""

    fileSelected = Signal(str)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("dropArea")
        self.setAcceptDrops(True)
        self.setCursor(Qt.PointingHandCursor)
        self.setMinimumHeight(190)
        self._drag_active = False

        layout = QVBoxLayout(self)
        layout.setAlignment(Qt.AlignCenter)
        layout.setSpacing(6)

        icon = QLabel("⇩")
        icon.setObjectName("dropIcon")
        icon.setAlignment(Qt.AlignCenter)
        icon.setStyleSheet("color:#9db3d6;")

        title = QLabel("把视频拖到这里")
        title.setObjectName("dropTitle")
        title.setAlignment(Qt.AlignCenter)

        hint = QLabel("支持 mp4 / mkv / mov / avi / flv / mp3 / wav 等，单个文件即可，6 小时也不怕")
        hint.setObjectName("dropHint")
        hint.setAlignment(Qt.AlignCenter)

        self.pick = QLabel("或点击选择文件")
        self.pick.setObjectName("dropHint")
        self.pick.setAlignment(Qt.AlignCenter)
        self.pick.setStyleSheet("color:#2563eb;")

        for w in (icon, title, hint, self.pick):
            layout.addWidget(w)

    # -- 拖拽 -----------------------------------------------------
    def dragEnterEvent(self, event: QDragEnterEvent) -> None:
        if self._urls(event.mimeData().urls()):
            event.acceptProposedAction()
            self._set_active(True)
        else:
            event.ignore()

    def dragLeaveEvent(self, event) -> None:  # noqa: N802
        self._set_active(False)
        super().dragLeaveEvent(event)

    def dropEvent(self, event: QDropEvent) -> None:  # noqa: N802
        self._set_active(False)
        urls = self._urls(event.mimeData().urls())
        if urls:
            event.acceptProposedAction()
            self.fileSelected.emit(urls[0])

    def mousePressEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        if event.button() == Qt.LeftButton:
            self._browse()
        super().mousePressEvent(event)

    def _browse(self) -> None:
        patterns = " ".join(f"*{ext}" for ext in sorted(SUPPORTED_EXTENSIONS))
        path, _ = QFileDialog.getOpenFileName(
            self, "选择视频或音频文件", "", f"媒体文件 ({patterns});;所有文件 (*.*)"
        )
        if path:
            self.fileSelected.emit(path)

    @staticmethod
    def _urls(urls) -> list[str]:
        out: list[str] = []
        for url in urls:
            if not url.isLocalFile():
                continue
            path = Path(url.toLocalFile())
            if path.suffix.lower() in SUPPORTED_EXTENSIONS and path.is_file():
                out.append(str(path))
        return out

    def _set_active(self, active: bool) -> None:
        self._drag_active = active
        self.setProperty("dragActive", "true" if active else "false")
        self.style().unpolish(self)
        self.style().polish(self)
        self.update()

    def paintEvent(self, event) -> None:  # noqa: N802
        super().paintEvent(event)
        if not self._drag_active:
            return
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        pen = QPen(QColor("#2563eb"))
        pen.setWidth(2)
        pen.setStyle(Qt.DashLine)
        painter.setPen(pen)
        painter.drawRoundedRect(self.rect().adjusted(2, 2, -2, -2), 12, 12)


def file_meta_text(path: Path, duration_text: str, size_bytes: int, width: int, height: int) -> str:
    bits = [duration_text, format_size(size_bytes)]
    if width and height:
        bits.append(f"{width}×{height}")
    bits.append(path.suffix.lstrip(".").upper())
    return "  ·  ".join(bits)
