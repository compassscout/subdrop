"""转录页：拖入 → 显示信息 → 开始 → 进度 → 出字幕。"""

from __future__ import annotations

import time
from pathlib import Path

from PySide6.QtCore import Qt, QTimer, QUrl, Signal
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPlainTextEdit,
    QProgressBar,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from ..config import Settings
from ..core.asr import build_provider
from ..core.asr.base import ASRError
from ..core.media import MediaError, MediaInfo, probe
from ..core.pipeline import TranscribeJob
from .widgets import Card, DropArea, file_meta_text, muted, page_title, subtitle
from .worker import TranscribeWorker


class TranscribePage(QWidget):
    openSettingsRequested = Signal()

    def __init__(self, settings: Settings, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.settings = settings
        self.path: Path | None = None
        self.info: MediaInfo | None = None
        self.worker: TranscribeWorker | None = None
        self._started_at = 0.0
        self._last_percent = 0.0

        root = QVBoxLayout(self)
        root.setContentsMargins(30, 26, 30, 26)
        root.setSpacing(14)

        root.addWidget(page_title("转录"))
        root.addWidget(
            subtitle("把本地视频拖进来，直接生成同名 .srt。默认云端识别，速度快、不吃显卡。")
        )

        self.drop = DropArea()
        self.drop.fileSelected.connect(self.load_file)
        root.addWidget(self.drop)

        # 文件信息卡（选中文件后才出现）
        self.file_card = Card()
        self.file_card.setVisible(False)

        self.name_label = QLabel()
        self.name_label.setObjectName("fileName")
        self.name_label.setWordWrap(True)
        self.meta_label = QLabel()
        self.meta_label.setObjectName("statValue")
        self.output_label = muted()

        self.file_card.layout.addWidget(self.name_label)
        self.file_card.layout.addWidget(self.meta_label)
        self.file_card.layout.addWidget(self.output_label)
        root.addWidget(self.file_card)

        # 操作按钮
        actions = QHBoxLayout()
        actions.setSpacing(10)
        self.start_button = QPushButton("开始转录")
        self.start_button.setObjectName("primary")
        self.start_button.setEnabled(False)
        self.start_button.clicked.connect(self.start_job)

        self.cancel_button = QPushButton("取消")
        self.cancel_button.setObjectName("ghost")
        self.cancel_button.setVisible(False)
        self.cancel_button.clicked.connect(self.cancel_job)

        self.open_button = QPushButton("打开字幕")
        self.open_button.setObjectName("ghost")
        self.open_button.setVisible(False)
        self.open_button.clicked.connect(self._open_output)

        self.folder_button = QPushButton("打开所在文件夹")
        self.folder_button.setObjectName("ghost")
        self.folder_button.setEnabled(False)
        self.folder_button.clicked.connect(self._open_folder)

        actions.addWidget(self.start_button)
        actions.addWidget(self.cancel_button)
        actions.addWidget(self.open_button)
        actions.addStretch(1)
        actions.addWidget(self.folder_button)
        root.addLayout(actions)

        # 进度
        self.status_label = QLabel("等待文件")
        self.status_label.setObjectName("statValue")
        self.percent_label = QLabel("")
        self.percent_label.setObjectName("muted")
        self.percent_label.setAlignment(Qt.AlignRight | Qt.AlignVCenter)

        status_row = QHBoxLayout()
        status_row.addWidget(self.status_label, 1)
        status_row.addWidget(self.percent_label)
        root.addLayout(status_row)

        self.progress = QProgressBar()
        self.progress.setRange(0, 1000)
        self.progress.setValue(0)
        root.addWidget(self.progress)

        self.log = QPlainTextEdit()
        self.log.setObjectName("log")
        self.log.setReadOnly(True)
        self.log.setMinimumHeight(110)
        self.log.setMaximumHeight(160)
        root.addWidget(self.log)

        root.addStretch(1)

        # 让整页也能接收拖放
        self.setAcceptDrops(True)

        self.timer = QTimer(self)
        self.timer.setInterval(500)
        self.timer.timeout.connect(self._tick)
        self._output_path: Path | None = None

    # -- 拖放（页面空白处也能拖） --------------------------------
    def dragEnterEvent(self, event) -> None:  # noqa: N802
        if self.drop._urls(event.mimeData().urls()):  # noqa: SLF001
            event.acceptProposedAction()

    def dropEvent(self, event) -> None:  # noqa: N802
        urls = self.drop._urls(event.mimeData().urls())  # noqa: SLF001
        if urls:
            event.acceptProposedAction()
            self.load_file(urls[0])

    # -- 选择文件 ------------------------------------------------
    def load_file(self, raw_path: str) -> None:
        if self.worker is not None:
            return
        path = Path(raw_path)
        try:
            info = probe(path, self.settings.ffmpeg_dir)
        except MediaError as exc:
            QMessageBox.warning(self, "读不了这个文件", str(exc))
            return

        self.path = path
        self.info = info
        self._output_path = None
        self.name_label.setText(path.name)
        self.meta_label.setText(
            file_meta_text(path, info.duration_text, path.stat().st_size, info.width, info.height)
        )
        self.output_label.setText(f"将输出到：{path.with_suffix('.' + (self.settings.output_format or 'srt')).name}")
        self.file_card.setVisible(True)
        self.start_button.setEnabled(True)
        self.folder_button.setEnabled(True)
        self.open_button.setVisible(False)
        self.progress.setValue(0)
        self.status_label.setText("准备就绪")
        self.percent_label.setText("")
        self._append_log(f"已选择：{path.name}（{info.duration_text}）")
        if not info.has_audio:
            self._append_log("警告：这个文件似乎没有音轨")

    # -- 开始 / 取消 ---------------------------------------------
    def start_job(self) -> None:
        if not self.path or not self.info or self.worker is not None:
            return
        if self.settings.provider != "mock" and not self.settings.api_key.strip():
            box = QMessageBox(self)
            box.setWindowTitle("还没配置识别服务")
            box.setText("当前是云端识别，需要先填一个 API Key。")
            box.setInformativeText("去「设置」里选服务商并粘贴 Key，之后就不用再管了。")
            goto = box.addButton("去设置", QMessageBox.AcceptRole)
            box.addButton("取消", QMessageBox.RejectRole)
            box.exec()
            if box.clickedButton() is goto:
                self.openSettingsRequested.emit()
            return

        try:
            provider = build_provider(self.settings)
        except ASRError as exc:
            QMessageBox.warning(self, "配置不完整", str(exc))
            self.openSettingsRequested.emit()
            return

        job = TranscribeJob(self.path, self.settings, provider)
        self.worker = TranscribeWorker(job, self)
        self.worker.progress.connect(self._on_progress)
        self.worker.log.connect(self._append_log)
        self.worker.succeeded.connect(self._on_done)
        self.worker.failed.connect(self._on_failed)
        self.worker.finished.connect(self._on_thread_finished)

        self._set_busy(True)
        self._started_at = time.time()
        self._last_percent = 0.0
        self.log.clear()
        self._append_log("开始转录")
        self.timer.start()
        self.progress.setValue(0)
        self.status_label.setText("准备中…")
        self.worker.start()

    def cancel_job(self) -> None:
        if self.worker is not None:
            self._append_log("正在取消…")
            self.cancel_button.setEnabled(False)
            self.worker.cancel()

    # -- 回调 ----------------------------------------------------
    def _on_progress(self, percent: float, message: str) -> None:
        self.progress.setValue(int(max(0.0, min(1.0, percent)) * 1000))
        self.status_label.setText(message)
        self.percent_label.setText(f"{percent * 100:.0f}%")
        self._last_percent = percent

    def _on_done(self, result) -> None:
        self.timer.stop()
        self._output_path = result.output
        elapsed = result.elapsed
        self._append_log(
            f"完成：{result.output.name} · {len(result.segments)} 条字幕 · {result.char_count} 字"
        )
        self._append_log(f"总耗时 {elapsed:.1f} 秒")
        self.status_label.setText(f"完成 · {len(result.segments)} 条字幕")
        self.percent_label.setText("100%")
        self.progress.setValue(1000)
        self.open_button.setVisible(True)
        self._set_busy(False)
        QMessageBox.information(
            self,
            "转录完成",
            f"字幕已生成：\n{result.output}\n\n"
            f"{len(result.segments)} 条 · {result.char_count} 字 · 耗时 {elapsed:.1f} 秒",
        )

    def _on_failed(self, message: str) -> None:
        self.timer.stop()
        self._set_busy(False)
        if message == "已取消":
            self.status_label.setText("已取消")
            self.percent_label.setText("")
            self._append_log("任务已取消，已完成的块会保留，下次可续跑")
            return
        self.status_label.setText("失败")
        self._append_log(f"失败：{message}")
        QMessageBox.warning(self, "转录失败", message)

    def _on_thread_finished(self) -> None:
        if self.worker is not None:
            self.worker.deleteLater()
            self.worker = None

    def _tick(self) -> None:
        elapsed = time.time() - self._started_at
        eta = ""
        if self._last_percent > 0.03:
            total = elapsed / self._last_percent
            eta = f" · 预计还需 {_mmss(max(0, total - elapsed))}"
        self.percent_label.setText(f"{self._last_percent * 100:.0f}%{eta}")

    # -- 状态 ----------------------------------------------------
    def _set_busy(self, busy: bool) -> None:
        self.start_button.setVisible(not busy)
        self.start_button.setEnabled(not busy and self.path is not None)
        self.cancel_button.setVisible(busy)
        self.cancel_button.setEnabled(busy)
        self.drop.setEnabled(not busy)
        self.folder_button.setEnabled(not busy and self.path is not None)

    def _append_log(self, message: str) -> None:
        stamp = time.strftime("%H:%M:%S")
        self.log.appendPlainText(f"[{stamp}] {message}")

    def _open_output(self) -> None:
        if self._output_path:
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(self._output_path)))

    def _open_folder(self) -> None:
        target = self.path.parent if self.path else None
        if target:
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(target)))


def _mmss(seconds: float) -> str:
    seconds = int(seconds)
    h, rem = divmod(seconds, 3600)
    m, s = divmod(rem, 60)
    if h:
        return f"{h}:{m:02d}:{s:02d}"
    return f"{m}:{s:02d}"
