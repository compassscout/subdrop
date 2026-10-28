"""主窗口：左侧导航，右侧内容。"""

from __future__ import annotations

from PySide6.QtCore import QSize, Qt
from PySide6.QtWidgets import (
    QButtonGroup,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QPushButton,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from .. import __version__
from ..config import Settings
from .placeholder import PlaceholderPage
from .settings_page import SettingsPage
from .transcribe_page import TranscribePage

NAV_ITEMS = [
    ("转录", "把本地视频变成字幕文件", False),
    ("批量处理", "一次拖入多个文件，排队转录", True),
    ("字幕翻译", "在已有字幕上做双语翻译", True),
    ("视频下载", "粘贴链接，先下视频再转录", True),
    ("设置", "识别服务、ffmpeg、输出格式", False),
]


class MainWindow(QMainWindow):
    def __init__(self, settings: Settings) -> None:
        super().__init__()
        self.settings = settings
        self.setWindowTitle("SubDrop — 拖进去，出字幕")
        self.resize(1060, 730)
        self.setMinimumSize(900, 620)

        root = QWidget()
        root.setObjectName("root")
        self.setCentralWidget(root)

        layout = QHBoxLayout(root)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        layout.addWidget(self._build_sidebar())

        self.stack = QStackedWidget()
        layout.addWidget(self.stack, 1)

        self.transcribe_page = TranscribePage(settings, self)
        self.transcribe_page.openSettingsRequested.connect(lambda: self._select(4))

        self.settings_page = SettingsPage(settings, self)
        self.settings_page.saved.connect(self._on_settings_saved)

        self.stack.addWidget(self.transcribe_page)
        self.stack.addWidget(
            PlaceholderPage(
                "批量处理",
                "拖一堆视频进来，排队跑完再统一收字幕。",
                [
                    "多文件排队，可暂停、可调顺序",
                    "每个任务独立进度与失败重试",
                    "完成后一键打开全部输出目录",
                ],
            )
        )
        self.stack.addWidget(
            PlaceholderPage(
                "字幕翻译",
                "把生成的中文/英文 SRT 翻成双语字幕。",
                [
                    "复用现有 SRT，只翻译不重新识别",
                    "双语对照 / 单语两种输出",
                    "术语表，保证人名和专有名词一致",
                ],
            )
        )
        self.stack.addWidget(
            PlaceholderPage(
                "视频下载",
                "粘贴 B 站 / YouTube 链接，下载完直接进转录队列。",
                [
                    "yt-dlp 作为可选依赖，不装也能用其它功能",
                    "自动挑选音轨，不下载整个视频流",
                    "复用浏览器 Cookie 处理需要登录的视频",
                ],
            )
        )
        self.stack.addWidget(self.settings_page)

        self._select(0)

    # -- 侧边栏 --------------------------------------------------
    def _build_sidebar(self) -> QWidget:
        sidebar = QWidget()
        sidebar.setObjectName("sidebar")
        sidebar.setFixedWidth(212)

        box = QVBoxLayout(sidebar)
        box.setContentsMargins(16, 22, 16, 16)
        box.setSpacing(6)

        brand = QLabel("SubDrop")
        brand.setObjectName("brand")
        box.addWidget(brand)

        sub = QLabel("拖进去，出字幕")
        sub.setObjectName("brandSub")
        box.addWidget(sub)
        box.addSpacing(18)

        self.nav_group = QButtonGroup(self)
        self.nav_group.setExclusive(True)
        self.nav_buttons: list[QPushButton] = []

        for index, (title, tip, coming) in enumerate(NAV_ITEMS):
            button = QPushButton(title)
            button.setObjectName("navButton")
            button.setCheckable(True)
            button.setCursor(Qt.PointingHandCursor)
            button.setToolTip(f"{tip}（规划中）" if coming else tip)
            button.clicked.connect(lambda _=False, i=index: self._select(i))
            self.nav_group.addButton(button, index)
            box.addWidget(button)
            self.nav_buttons.append(button)
            if coming:
                hint = QLabel("即将推出")
                hint.setObjectName("navHint")
                hint.setContentsMargins(12, 0, 0, 6)
                box.addWidget(hint)

        box.addStretch(1)
        version = QLabel(f"v{__version__} · MIT")
        version.setObjectName("version")
        box.addWidget(version)

        credit = QLabel("界面参考 VideoCaptioner 的体验")
        credit.setObjectName("version")
        credit.setWordWrap(True)
        box.addWidget(credit)
        return sidebar

    def _select(self, index: int) -> None:
        self.stack.setCurrentIndex(index)
        if 0 <= index < len(self.nav_buttons):
            self.nav_buttons[index].setChecked(True)

    def _on_settings_saved(self) -> None:
        if self.transcribe_page.path and self.transcribe_page.info:
            fmt = self.settings.output_format or "srt"
            base = self.transcribe_page.path
            self.transcribe_page.output_label.setText(
                f"将输出到：{base.with_suffix('.' + fmt).name}"
            )

    def sizeHint(self) -> QSize:  # noqa: N802
        return QSize(1060, 730)
