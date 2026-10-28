"""设置页：把「填一次，以后不用管」的配置集中在一个页面。"""

from __future__ import annotations

from PySide6.QtCore import Qt, QThread, QUrl, Signal
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QLineEdit,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from ..config import CONFIG_PATH, LANGUAGES, PROVIDER_PRESETS, Settings
from ..core.media import MediaError, resolve_tool
from .widgets import Card, muted, page_title, subtitle


class TestWorker(QThread):
    done = Signal(bool, str)

    def __init__(self, base_url: str, api_key: str, parent=None) -> None:
        super().__init__(parent)
        self.base_url = base_url
        self.api_key = api_key

    def run(self) -> None:
        import requests

        base = self.base_url.rstrip("/")
        url = f"{base}/models"
        try:
            resp = requests.get(
                url,
                headers={"Authorization": f"Bearer {self.api_key}"},
                timeout=(6, 12),
            )
        except requests.RequestException as exc:
            self.done.emit(False, f"连不上：{exc}")
            return
        if resp.status_code == 200:
            try:
                count = len(resp.json().get("data", []))
            except ValueError:
                count = 0
            self.done.emit(True, f"连接成功，服务端返回 {count} 个模型" if count else "连接成功")
        elif resp.status_code == 401:
            self.done.emit(False, "Key 无效（401）")
        elif resp.status_code == 404:
            self.done.emit(False, "地址不对（404），检查 Base URL 是否以 /v1 结尾")
        else:
            self.done.emit(False, f"服务端返回 {resp.status_code}")


class SettingsPage(QWidget):
    saved = Signal()

    def __init__(self, settings: Settings, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.settings = settings
        self._test_worker: TestWorker | None = None

        root = QVBoxLayout(self)
        root.setContentsMargins(30, 26, 30, 26)
        root.setSpacing(14)
        root.addWidget(page_title("设置"))
        root.addWidget(subtitle("只需要配置一次。Key 只存在本机的配置文件里，不会上传到任何地方。"))

        card = Card()
        form = QFormLayout()
        form.setLabelAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        form.setFormAlignment(Qt.AlignLeft | Qt.AlignTop)
        form.setHorizontalSpacing(24)
        form.setVerticalSpacing(12)

        self.provider = QComboBox()
        for key, preset in PROVIDER_PRESETS.items():
            self.provider.addItem(preset["label"], key)
        self.provider.currentIndexChanged.connect(self._apply_preset)

        self.base_url = QLineEdit()
        self.base_url.setPlaceholderText("https://api.groq.com/openai/v1")

        self.api_key = QLineEdit()
        self.api_key.setEchoMode(QLineEdit.Password)
        self.api_key.setPlaceholderText("粘贴你的 API Key")

        key_row = QHBoxLayout()
        key_row.setSpacing(6)
        key_row.addWidget(self.api_key, 1)
        self.show_key = QCheckBox("显示")
        self.show_key.toggled.connect(
            lambda on: self.api_key.setEchoMode(QLineEdit.Normal if on else QLineEdit.Password)
        )
        key_row.addWidget(self.show_key)
        key_box = QWidget()
        key_box.setLayout(key_row)
        key_row.setContentsMargins(0, 0, 0, 0)

        self.signup = QPushButton("去申请免费 Key →")
        self.signup.setObjectName("link")
        self.signup.setCursor(Qt.PointingHandCursor)
        self.signup.clicked.connect(self._open_signup)

        self.provider_note = muted("")
        self.provider_note.setVisible(False)

        self.model = QLineEdit()
        self.model.setPlaceholderText("whisper-large-v3-turbo")

        self.language = QComboBox()
        for code, label in LANGUAGES:
            self.language.addItem(label, code)

        self.chunk = QSpinBox()
        self.chunk.setRange(60, 1800)
        self.chunk.setSingleStep(60)
        self.chunk.setSuffix(" 秒")
        self.chunk.setToolTip("越大越快，但单次请求体积也越大。默认 600 秒比较稳。")

        self.output_format = QComboBox()
        for fmt, label in (("srt", "SRT（通用）"), ("vtt", "VTT（网页）"), ("txt", "TXT（只要文字）")):
            self.output_format.addItem(label, fmt)

        self.ffmpeg_dir = QLineEdit()
        self.ffmpeg_dir.setPlaceholderText("留空则使用 PATH 里的 ffmpeg")
        browse = QPushButton("浏览")
        browse.setObjectName("ghost")
        browse.clicked.connect(self._pick_ffmpeg_dir)
        ff_row = QHBoxLayout()
        ff_row.setSpacing(6)
        ff_row.addWidget(self.ffmpeg_dir, 1)
        ff_row.addWidget(browse)
        ff_box = QWidget()
        ff_box.setLayout(ff_row)
        ff_row.setContentsMargins(0, 0, 0, 0)

        self.keep_audio = QCheckBox("保留临时音频块（排查问题用，默认不保留）")

        self.ffmpeg_status = muted("正在检测 ffmpeg…")

        form.addRow(muted("服务商"), self.provider)
        form.addRow(muted("接口地址"), self.base_url)
        form.addRow(muted("API Key"), key_box)
        form.addRow("", self.signup)
        form.addRow("", self.provider_note)
        form.addRow(muted("模型"), self.model)
        form.addRow(muted("识别语言"), self.language)
        form.addRow(muted("分块时长"), self.chunk)
        form.addRow(muted("输出格式"), self.output_format)
        form.addRow(muted("ffmpeg 目录"), ff_box)
        form.addRow("", self.keep_audio)
        form.addRow("", self.ffmpeg_status)
        card.layout.addLayout(form)

        buttons = QHBoxLayout()
        buttons.setSpacing(10)
        self.save_button = QPushButton("保存设置")
        self.save_button.setObjectName("primary")
        self.save_button.clicked.connect(self._save)

        self.test_button = QPushButton("测试连接")
        self.test_button.setObjectName("ghost")
        self.test_button.clicked.connect(self._test)

        open_config = QPushButton("打开配置文件")
        open_config.setObjectName("ghost")
        open_config.clicked.connect(
            lambda: QDesktopServices.openUrl(QUrl.fromLocalFile(str(CONFIG_PATH)))
        )

        buttons.addWidget(self.save_button)
        buttons.addWidget(self.test_button)
        buttons.addStretch(1)
        buttons.addWidget(open_config)
        card.layout.addLayout(buttons)

        self.hint = muted("")
        card.layout.addWidget(self.hint)

        root.addWidget(card)
        root.addStretch(1)

        self._load()

    # -- 数据 ----------------------------------------------------
    def _load(self) -> None:
        s = self.settings
        index = self.provider.findData(s.provider)
        self.provider.blockSignals(True)
        self.provider.setCurrentIndex(max(0, index))
        self.provider.blockSignals(False)
        self.base_url.setText(s.base_url)
        self.api_key.setText(s.api_key)
        self.model.setText(s.model)
        lang_index = self.language.findData(s.language)
        self.language.setCurrentIndex(max(0, lang_index))
        self.chunk.setValue(max(60, s.chunk_seconds))
        fmt_index = self.output_format.findData(s.output_format)
        self.output_format.setCurrentIndex(max(0, fmt_index))
        self.ffmpeg_dir.setText(s.ffmpeg_dir)
        self.keep_audio.setChecked(s.keep_audio)
        self._update_signup()
        self._check_ffmpeg()

    def _apply_preset(self) -> None:
        key = self.provider.currentData()
        preset = PROVIDER_PRESETS.get(key or "", {})
        if preset.get("base_url"):
            self.base_url.setText(preset["base_url"])
        if preset.get("model"):
            self.model.setText(preset["model"])
        self._update_signup()

    def _update_signup(self) -> None:
        key = self.provider.currentData()
        preset = PROVIDER_PRESETS.get(key or "", {})
        url = preset.get("signup", "")
        self.signup.setVisible(bool(url))
        self.signup.setProperty("url", url)
        notes = {
            "groq": "国内网络通常需要代理；连不上就换「硅基流动」。",
            "openai": "国内网络需要代理；没有外币卡可以用硅基流动。",
        }
        note = notes.get(key or "", "")
        self.provider_note.setText(note)
        self.provider_note.setVisible(bool(note))

    def _open_signup(self) -> None:
        url = self.signup.property("url")
        if url:
            QDesktopServices.openUrl(QUrl(str(url)))

    def _pick_ffmpeg_dir(self) -> None:
        folder = QFileDialog.getExistingDirectory(self, "选择包含 ffmpeg.exe 的目录")
        if folder:
            self.ffmpeg_dir.setText(folder)
            self._check_ffmpeg()

    def _check_ffmpeg(self) -> None:
        try:
            path = resolve_tool("ffmpeg", self.ffmpeg_dir.text().strip())
        except MediaError:
            self.ffmpeg_status.setText("⚠ 没找到 ffmpeg，请先安装或指定目录")
            self.ffmpeg_status.setStyleSheet("color:#b91c1c;font-size:12px;")
            return
        self.ffmpeg_status.setText("✓ ffmpeg 已就绪，可以直接转录")
        self.ffmpeg_status.setToolTip(path)
        self.ffmpeg_status.setStyleSheet("color:#15803d;font-size:12px;")

    # -- 动作 ----------------------------------------------------
    def values(self) -> Settings:
        s = self.settings
        s.provider = self.provider.currentData() or "groq"
        s.base_url = self.base_url.text().strip()
        s.api_key = self.api_key.text().strip()
        s.model = self.model.text().strip()
        s.language = self.language.currentData() or "auto"
        s.chunk_seconds = int(self.chunk.value())
        s.output_format = self.output_format.currentData() or "srt"
        s.ffmpeg_dir = self.ffmpeg_dir.text().strip()
        s.keep_audio = self.keep_audio.isChecked()
        return s

    def _save(self) -> None:
        self.values()
        try:
            self.settings.save()
        except OSError as exc:
            self.hint.setText(f"保存失败：{exc}")
            return
        self.hint.setText(f"已保存到 {CONFIG_PATH}")
        self.saved.emit()

    def _test(self) -> None:
        if self._test_worker is not None:
            return
        key = self.api_key.text().strip()
        if not key:
            self.hint.setText("先填 API Key 再测试")
            return
        self.test_button.setEnabled(False)
        self.hint.setText("正在连接…")
        worker = TestWorker(self.base_url.text().strip(), key, self)
        worker.done.connect(self._on_test_done)
        worker.finished.connect(self._on_test_finished)
        self._test_worker = worker
        worker.start()

    def _on_test_done(self, ok: bool, message: str) -> None:
        self.hint.setText(("✓ " if ok else "✗ ") + message)
        self.hint.setStyleSheet(
            f"color:{'#15803d' if ok else '#b91c1c'};font-size:12px;"
        )

    def _on_test_finished(self) -> None:
        self.test_button.setEnabled(True)
        if self._test_worker is not None:
            self._test_worker.deleteLater()
            self._test_worker = None
