"""本地假后端：不联网，用来跑通流程和测试。"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from .base import Segment

SAMPLE_LINES = [
    "这是 SubDrop 的离线演示字幕。",
    "它不会上传任何音频，也不会消耗额度。",
    "真正的转录请到设置里填入 API Key。",
    "长视频会被切成多块，分别识别再拼回去。",
]


class MockProvider:
    name = "mock"

    def transcribe(
        self,
        audio: Path,
        *,
        language: str | None = None,
        should_cancel: Callable[[], bool] | None = None,
        duration: float | None = None,
    ) -> list[Segment]:
        total = float(duration or 12.0)
        step = total / len(SAMPLE_LINES)
        return [
            Segment(round(i * step, 2), round((i + 1) * step - 0.2, 2), line)
            for i, line in enumerate(SAMPLE_LINES)
        ]
