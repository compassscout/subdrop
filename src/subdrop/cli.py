"""命令行入口：不打开窗口也能转录，方便脚本化和排查问题。

注意：打包成 Windows 窗口程序后，进程可能没有有效的 stdout/stderr 句柄，
直接 print 会抛 OSError(22)。所以所有输出都走 _safe_stream 兜底，
写不出去就静默丢弃，而不是让转录任务跟着崩掉。
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from .config import Settings
from .core.asr import build_provider
from .core.asr.base import ASRError
from .core.asr.mock import MockProvider
from .core.media import MediaError
from .core.pipeline import Cancelled, TranscribeJob

_OUT = None
_ERR = None


def _safe_stream(name: str):
    stream = getattr(sys, name, None)
    if stream is None:
        return open(os.devnull, "w", encoding="utf-8")
    try:
        stream.write("")
        stream.flush()
    except (OSError, ValueError):
        return open(os.devnull, "w", encoding="utf-8")
    return stream


def _out(text: str = "", end: str = "\n") -> None:
    global _OUT
    if _OUT is None:
        _OUT = _safe_stream("stdout")
    try:
        _OUT.write(text + end)
        _OUT.flush()
    except (OSError, ValueError):
        pass


def _err(text: str, end: str = "\n") -> None:
    global _ERR
    if _ERR is None:
        _ERR = _safe_stream("stderr")
    try:
        _ERR.write(text + end)
        _ERR.flush()
    except (OSError, ValueError):
        pass


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="subdrop-cli",
        description="把本地视频转成 SRT 字幕（命令行版）",
    )
    parser.add_argument("source", type=Path, help="视频或音频文件")
    parser.add_argument("-o", "--output", type=Path, default=None, help="输出文件路径")
    parser.add_argument("--lang", default=None, help="语言代码，如 zh / en；默认用设置里的值")
    parser.add_argument("--chunk", type=int, default=None, help="分块时长（秒），默认 600")
    parser.add_argument("--format", default=None, choices=["srt", "txt", "vtt"])
    parser.add_argument("--model", default=None)
    parser.add_argument("--base-url", default=None)
    parser.add_argument("--api-key", default=None)
    parser.add_argument("--ffmpeg-dir", default=None)
    parser.add_argument("--keep-audio", action="store_true", help="保留临时的分块音频")
    parser.add_argument("--mock", action="store_true", help="使用离线假后端，仅用于跑通流程")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    settings = Settings.load()
    if args.lang:
        settings.language = args.lang
    if args.chunk:
        settings.chunk_seconds = args.chunk
    if args.format:
        settings.output_format = args.format
    if args.model:
        settings.model = args.model
    if args.base_url:
        settings.base_url = args.base_url
    if args.api_key:
        settings.api_key = args.api_key
    if args.ffmpeg_dir:
        settings.ffmpeg_dir = args.ffmpeg_dir
    if args.keep_audio:
        settings.keep_audio = True

    provider = MockProvider() if args.mock else None
    try:
        if provider is None:
            provider = build_provider(settings)
        job = TranscribeJob(args.source, settings, provider, output=args.output)
        result = job.run(
            on_progress=_print_progress,
            on_log=lambda msg: _err(f"  {msg}"),
        )
    except (ASRError, MediaError, Cancelled) as exc:
        _err(f"\n失败：{exc}")
        return 1

    _out(f"\n完成：{result.output}")
    _out(
        f"{len(result.segments)} 条字幕 / {result.char_count} 字 / "
        f"耗时 {result.elapsed:.1f}s"
    )
    return 0


def _print_progress(percent: float, message: str) -> None:
    bar_len = 24
    filled = int(bar_len * max(0.0, min(1.0, percent)))
    bar = "=" * filled + "-" * (bar_len - filled)
    _err(f"\r{bar} {percent * 100:5.1f}%  {message[:48]:<48}", end="")


if __name__ == "__main__":
    raise SystemExit(main())
