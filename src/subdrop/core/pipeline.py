"""转录流水线：探测 → 抽音分块 → 逐块识别 → 拼接 → 写 SRT。

设计上只做三件事，且都可中断、可续跑：
- 每一块识别完立刻落盘（chunk_XXXX.json），崩了/断电了重开能从断点继续；
- 临时音频按任务隔离，成功后默认删掉，不占 C 盘；
- 进度按块上报，6 小时视频也能给出像样的剩余时间。
"""

from __future__ import annotations

import hashlib
import json
import shutil
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

from ..config import Settings, cache_dir
from .asr.base import ASRError, Segment, normalize
from .cues import ChunkResult, join_chunks
from .media import MediaError, MediaInfo, extract_chunks, probe
from .srt import unique_output_path, write_subtitle


class Cancelled(RuntimeError):
    pass


@dataclass(slots=True)
class JobResult:
    source: Path
    output: Path
    segments: list[Segment]
    media: MediaInfo
    elapsed: float
    reused_chunks: int = 0
    metadata: dict = field(default_factory=dict)

    @property
    def char_count(self) -> int:
        return sum(len(s.text) for s in self.segments)


def _cache_key(src: Path, chunk_seconds: int) -> str:
    stat = src.stat()
    raw = f"{src.resolve()}|{stat.st_size}|{stat.st_mtime_ns}|{chunk_seconds}"
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()[:16]


class TranscribeJob:
    def __init__(
        self,
        source: Path,
        settings: Settings,
        provider,
        *,
        output: Path | None = None,
        work_root: Path | None = None,
    ) -> None:
        self.source = Path(source)
        self.settings = settings
        self.provider = provider
        self.output = Path(output) if output else None
        self.work_root = Path(work_root) if work_root else cache_dir() / "jobs"
        self._cancelled = False

    # -- 外部取消 -------------------------------------------------
    def cancel(self) -> None:
        self._cancelled = True

    def _check_cancel(self) -> None:
        if self._cancelled:
            raise Cancelled("已取消")

    # -- 主流程 ---------------------------------------------------
    def run(
        self,
        on_progress: Callable[[float, str], None] | None = None,
        on_log: Callable[[str], None] | None = None,
    ) -> JobResult:
        started = time.time()
        progress = on_progress or (lambda p, m: None)
        log = on_log or (lambda m: None)

        if not self.source.is_file():
            raise MediaError(f"文件不存在：{self.source}")

        log(f"读取媒体信息：{self.source.name}")
        media = probe(self.source, self.settings.ffmpeg_dir)
        log(f"时长 {media.duration_text}，{'含' if media.has_audio else '无'}音轨")
        if not media.has_audio:
            raise MediaError("这个文件没有音轨，无法转录")
        progress(0.03, "已读取媒体信息")

        key = _cache_key(self.source, self.settings.chunk_seconds)
        job_dir = self.work_root / key
        audio_dir = job_dir / "audio"
        job_dir.mkdir(parents=True, exist_ok=True)

        chunk_seconds = max(60, int(self.settings.chunk_seconds))
        expected = max(1, int(media.duration // chunk_seconds) + 1)
        chunks = self._ensure_chunks(audio_dir, media, chunk_seconds, expected, progress, log)
        self._check_cancel()

        cached = [self._load_chunk(job_dir, i) for i in range(len(chunks))]
        reused = sum(1 for c in cached if c is not None)
        if reused:
            log(f"发现 {reused} 块缓存，跳过重新识别")

        results: list[ChunkResult] = []
        offset = 0.0
        for index, audio in enumerate(chunks):
            self._check_cancel()
            chunk_len = self._chunk_duration(offset, media, chunk_seconds)
            cached_result = cached[index]
            if cached_result is not None:
                results.append(cached_result)
            else:
                log(f"识别第 {index + 1}/{len(chunks)} 块（{_fmt_sec(chunk_len)}）")
                try:
                    segments = self.provider.transcribe(
                        audio,
                        language=self.settings.language_value,
                        should_cancel=lambda: self._cancelled,
                        duration=chunk_len,
                    )
                except ASRError:
                    raise
                results.append(ChunkResult(offset, chunk_len, segments))
                self._save_chunk(job_dir, index, results[-1])
            offset += chunk_len
            done = (index + 1) / len(chunks)
            eta = ""
            elapsed = time.time() - started
            if done > 0.05:
                remaining = elapsed / done * (1 - done)
                eta = f"，预计还需 {_fmt_sec(remaining)}"
            progress(0.10 + 0.85 * done, f"已识别 {index + 1}/{len(chunks)} 块{eta}")

        segments = normalize(join_chunks(results))
        if not segments:
            raise ASRError("整段音频都没有识别出文字，检查音频是否有声音")

        fmt = self.settings.output_format or "srt"
        base = self.output or self.source.with_suffix("")
        out_path = unique_output_path(Path(base), fmt)
        write_subtitle(out_path, segments, fmt)
        log(f"字幕已写入：{out_path.name}（{len(segments)} 条）")
        progress(0.99, "写入字幕")

        if not self.settings.keep_audio:
            shutil.rmtree(audio_dir, ignore_errors=True)
        progress(1.0, "完成")

        return JobResult(
            source=self.source,
            output=out_path,
            segments=segments,
            media=media,
            elapsed=time.time() - started,
            reused_chunks=reused,
            metadata={"chunks": len(chunks), "cache_key": key},
        )

    # -- 内部 -----------------------------------------------------
    def _ensure_chunks(
        self,
        audio_dir: Path,
        media: MediaInfo,
        chunk_seconds: int,
        expected: int,
        progress: Callable[[float, str], None],
        log: Callable[[str], None],
    ) -> list[Path]:
        existing = sorted(audio_dir.glob("chunk_*.mp3")) if audio_dir.exists() else []
        if existing and len(existing) >= expected - 1:
            log(f"复用已提取的 {len(existing)} 块音频")
            return existing
        log("正在提取音轨并分块（16kHz 单声道，6 小时约 90MB）")
        chunks = extract_chunks(
            self.source,
            audio_dir,
            chunk_seconds=chunk_seconds,
            ffmpeg_dir=self.settings.ffmpeg_dir,
            on_progress=lambda sec: progress(
                0.03 + 0.07 * min(1.0, sec / max(media.duration, 1.0)),
                f"提取音频 {_fmt_sec(min(sec, media.duration))}/{media.duration_text}",
            ),
            should_cancel=lambda: self._cancelled,
        )
        log(f"音频已切成 {len(chunks)} 块")
        return chunks

    @staticmethod
    def _chunk_duration(offset: float, media: MediaInfo, chunk_seconds: int) -> float:
        """分块按固定时长切，只有最后一块按总时长收尾，不必再调用 ffmpeg 探测。"""
        remaining = media.duration - offset
        if remaining <= 0:
            return float(chunk_seconds)
        return max(0.5, min(float(chunk_seconds), remaining))

    @staticmethod
    def _load_chunk(job_dir: Path, index: int) -> ChunkResult | None:
        path = job_dir / f"chunk_{index:04d}.json"
        if not path.exists():
            return None
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
            segments = [
                Segment(float(s["start"]), float(s["end"]), str(s["text"])) for s in raw["segments"]
            ]
            return ChunkResult(float(raw["offset"]), float(raw["duration"]), segments)
        except (OSError, ValueError, KeyError, TypeError):
            return None

    @staticmethod
    def _save_chunk(job_dir: Path, index: int, result: ChunkResult) -> None:
        path = job_dir / f"chunk_{index:04d}.json"
        payload = {
            "offset": result.offset,
            "duration": result.duration,
            "segments": [
                {"start": s.start, "end": s.end, "text": s.text} for s in result.segments
            ],
        }
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
        tmp.replace(path)


def _fmt_sec(seconds: float) -> str:
    seconds = max(0, int(round(seconds)))
    h, rem = divmod(seconds, 3600)
    m, s = divmod(rem, 60)
    if h:
        return f"{h} 小时 {m} 分"
    if m:
        return f"{m} 分 {s} 秒"
    return f"{s} 秒"
