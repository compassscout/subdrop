"""把流水线放到后台线程，UI 不卡。"""

from __future__ import annotations

from PySide6.QtCore import QThread, Signal

from ..core.asr.base import ASRError
from ..core.media import MediaError
from ..core.pipeline import Cancelled, TranscribeJob


class TranscribeWorker(QThread):
    progress = Signal(float, str)
    log = Signal(str)
    succeeded = Signal(object)
    failed = Signal(str)

    def __init__(self, job: TranscribeJob, parent=None) -> None:
        super().__init__(parent)
        self.job = job

    def run(self) -> None:
        try:
            result = self.job.run(
                on_progress=lambda p, m: self.progress.emit(p, m),
                on_log=self.log.emit,
            )
        except Cancelled:
            self.failed.emit("已取消")
        except (ASRError, MediaError) as exc:
            self.failed.emit(str(exc))
        except Exception as exc:  # noqa: BLE001 - 兜底，避免线程静默死亡
            self.failed.emit(f"{type(exc).__name__}: {exc}")
        else:
            self.succeeded.emit(result)

    def cancel(self) -> None:
        self.job.cancel()
