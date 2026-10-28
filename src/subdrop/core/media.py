"""媒体层：ffprobe 读时长，ffmpeg 抽音轨并切块。

长视频的第一原则：整段音频不要一次性读进内存。这里统一走
`ffmpeg -f segment`，直接产出 10 分钟左右的 mp3 小块，边转边删。
"""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

VIDEO_EXTENSIONS = {
    ".mp4", ".mkv", ".mov", ".avi", ".flv", ".wmv", ".webm", ".m4v",
    ".ts", ".mts", ".mpg", ".mpeg", ".3gp",
}
AUDIO_EXTENSIONS = {".mp3", ".wav", ".m4a", ".aac", ".flac", ".ogg", ".opus", ".wma"}
SUPPORTED_EXTENSIONS = VIDEO_EXTENSIONS | AUDIO_EXTENSIONS

CREATE_NO_WINDOW = 0x08000000 if sys.platform == "win32" else 0


class MediaError(RuntimeError):
    pass


@dataclass(slots=True)
class MediaInfo:
    path: Path
    duration: float
    has_audio: bool
    width: int = 0
    height: int = 0

    @property
    def duration_text(self) -> str:
        total = int(round(self.duration))
        h, rem = divmod(total, 3600)
        m, s = divmod(rem, 60)
        return f"{h}:{m:02d}:{s:02d}" if h else f"{m}:{s:02d}"


def _bundled_dirs() -> list[Path]:
    dirs: list[Path] = []
    if getattr(sys, "frozen", False):
        exe_dir = Path(sys.executable).resolve().parent
        dirs += [exe_dir, exe_dir / "resources", exe_dir / "_internal"]
    here = Path(__file__).resolve()
    dirs += [here.parents[2] / "resources", here.parents[3] / "resources"]
    return dirs


def resolve_tool(name: str, ffmpeg_dir: str = "") -> str:
    """按 配置目录 → 打包目录 → PATH 的顺序找 ffmpeg/ffprobe。"""
    exe = f"{name}.exe" if sys.platform == "win32" else name
    candidates: list[Path] = []
    if ffmpeg_dir:
        candidates += [Path(ffmpeg_dir) / exe, Path(ffmpeg_dir) / name]
    for d in _bundled_dirs():
        candidates.append(d / exe)
    for c in candidates:
        if c.is_file():
            return str(c)
    found = shutil.which(name)
    if found:
        return found
    raise MediaError(
        f"找不到 {name}。请安装 ffmpeg 并加入 PATH，或在设置里指定 ffmpeg 所在目录。"
    )


def _run(cmd: list[str]) -> subprocess.CompletedProcess:
    return subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        creationflags=CREATE_NO_WINDOW,
    )


def probe(path: Path, ffmpeg_dir: str = "") -> MediaInfo:
    ffprobe = resolve_tool("ffprobe", ffmpeg_dir)
    proc = _run([
        ffprobe, "-v", "error",
        "-show_entries", "format=duration:stream=codec_type,width,height",
        "-of", "json", str(path),
    ])
    if proc.returncode != 0:
        raise MediaError(f"无法读取媒体信息：{proc.stderr.strip()[:300]}")
    try:
        data = json.loads(proc.stdout or "{}")
    except json.JSONDecodeError as exc:
        raise MediaError("ffprobe 返回了无法解析的内容") from exc

    duration = float(data.get("format", {}).get("duration") or 0.0)
    streams = data.get("streams", [])
    has_audio = any(s.get("codec_type") == "audio" for s in streams)
    width = next((int(s.get("width") or 0) for s in streams if s.get("codec_type") == "video"), 0)
    height = next((int(s.get("height") or 0) for s in streams if s.get("codec_type") == "video"), 0)
    if duration <= 0:
        raise MediaError("读不到时长，文件可能已损坏或不是音视频文件")
    return MediaInfo(path=path, duration=duration, has_audio=has_audio, width=width, height=height)


def extract_chunks(
    src: Path,
    out_dir: Path,
    chunk_seconds: int = 600,
    ffmpeg_dir: str = "",
    on_progress: Callable[[float], None] | None = None,
    should_cancel: Callable[[], bool] | None = None,
) -> list[Path]:
    """把音轨转成 16k 单声道 32kbps mp3，并按 chunk_seconds 切块。"""
    ffmpeg = resolve_tool("ffmpeg", ffmpeg_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    for old in out_dir.glob("chunk_*.mp3"):
        old.unlink(missing_ok=True)

    pattern = out_dir / "chunk_%04d.mp3"
    cmd = [
        ffmpeg, "-hide_banner", "-nostdin", "-y",
        "-i", str(src),
        "-vn", "-sn", "-dn",
        "-ac", "1", "-ar", "16000", "-c:a", "libmp3lame", "-b:a", "32k",
        "-f", "segment", "-segment_time", str(max(60, int(chunk_seconds))),
        "-reset_timestamps", "1",
        "-progress", "pipe:1", "-nostats",
        str(pattern),
    ]
    proc = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
        errors="replace",
        creationflags=CREATE_NO_WINDOW,
    )
    tail: list[str] = []
    assert proc.stdout is not None
    try:
        for line in proc.stdout:
            line = line.strip()
            if not line:
                continue
            if line.startswith("out_time_us=") or line.startswith("out_time_ms="):
                raw = line.split("=", 1)[1]
                if raw.isdigit() and on_progress:
                    on_progress(int(raw) / 1_000_000.0)
            elif line.startswith("progress="):
                continue
            else:
                tail.append(line)
                del tail[:-25]
            if should_cancel and should_cancel():
                proc.terminate()
                raise MediaError("已取消")
    finally:
        proc.wait()
        if proc.stdout:
            proc.stdout.close()

    if proc.returncode != 0:
        detail = "\n".join(tail[-8:]) or f"退出码 {proc.returncode}"
        raise MediaError(f"音频提取失败：{detail}")

    chunks = sorted(out_dir.glob("chunk_*.mp3"))
    if not chunks:
        raise MediaError("没有提取到任何音频，可能该文件不含音轨")
    return chunks


def format_size(num_bytes: int) -> str:
    size = float(num_bytes)
    for unit in ("B", "KB", "MB", "GB"):
        if size < 1024 or unit == "GB":
            return f"{size:.0f} {unit}" if unit == "B" else f"{size:.1f} {unit}"
        size /= 1024
    return f"{size:.1f} GB"
