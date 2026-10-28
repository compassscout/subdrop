"""ASR 抽象：所有后端都只需要吐出一串带时间戳的 Segment。"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol, runtime_checkable


class ASRError(RuntimeError):
    pass


@dataclass(slots=True)
class Segment:
    start: float
    end: float
    text: str

    def shifted(self, offset: float) -> Segment:
        return Segment(self.start + offset, self.end + offset, self.text)

    @property
    def duration(self) -> float:
        return max(0.0, self.end - self.start)


@runtime_checkable
class ASRProvider(Protocol):
    name: str

    def transcribe(
        self,
        audio: Path,
        *,
        language: str | None = None,
        should_cancel: Callable[[], bool] | None = None,
    ) -> list[Segment]: ...


def normalize(segments: list[Segment], min_duration: float = 0.25) -> list[Segment]:
    """排序、去空、修掉重叠与零长度。"""
    cleaned: list[Segment] = []
    for seg in sorted(segments, key=lambda s: (s.start, s.end)):
        text = " ".join(seg.text.split())
        if not text:
            continue
        start = max(0.0, float(seg.start))
        end = float(seg.end)
        if end <= start:
            end = start + min_duration
        cleaned.append(Segment(start, end, text))

    for i in range(len(cleaned) - 1):
        cur, nxt = cleaned[i], cleaned[i + 1]
        if cur.end > nxt.start - 0.02:
            cur.end = max(cur.start + min_duration, nxt.start - 0.02)
    return [s for s in cleaned if s.end > s.start]
