"""SRT / TXT 输出。"""

from __future__ import annotations

from pathlib import Path

from .asr.base import Segment


def format_timestamp(seconds: float) -> str:
    if seconds < 0:
        seconds = 0.0
    millis = int(round(seconds * 1000))
    hours, millis = divmod(millis, 3_600_000)
    minutes, millis = divmod(millis, 60_000)
    secs, millis = divmod(millis, 1000)
    return f"{hours:02d}:{minutes:02d}:{secs:02d},{millis:03d}"


def segments_to_srt(segments: list[Segment]) -> str:
    blocks: list[str] = []
    for index, seg in enumerate(segments, start=1):
        text = seg.text.strip()
        if not text:
            continue
        blocks.append(
            f"{index}\n"
            f"{format_timestamp(seg.start)} --> {format_timestamp(seg.end)}\n"
            f"{text}\n"
        )
    return "\n".join(blocks)


def segments_to_txt(segments: list[Segment]) -> str:
    return "\n".join(seg.text.strip() for seg in segments if seg.text.strip())


def write_subtitle(path: Path, segments: list[Segment], fmt: str = "srt") -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    if fmt == "txt":
        content = segments_to_txt(segments) + "\n"
    elif fmt == "vtt":
        body = segments_to_srt(segments).replace(",", ".")
        content = "WEBVTT\n\n" + body
    else:
        content = segments_to_srt(segments)
    path.write_text(content, encoding="utf-8")
    return path


def unique_output_path(base: Path, fmt: str = "srt") -> Path:
    """不覆盖已有文件：a.srt → a.1.srt → a.2.srt。"""
    candidate = base.with_suffix(f".{fmt}")
    if not candidate.exists():
        return candidate
    for i in range(1, 1000):
        alt = base.with_name(f"{base.name}.{i}.{fmt}")
        if not alt.exists():
            return alt
    return candidate
