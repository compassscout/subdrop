"""媒体层：读时长、抽音轨、切块。

只依赖一个 ffmpeg 可执行文件（不依赖 ffprobe），因为打包时每多一个
200MB 的静态二进制都是灾难。媒体信息从 `ffmpeg -i` 的 stderr 里解析，
足够我们判断时长、有没有音轨、分辨率。

长视频的第一原则：整段音频不要一次性读进内存。这里统一走
`ffmpeg -f segment`，直接产出 10 分钟左右的 mp3 小块，边转边删。
"""

from __future__ import annotations

import re
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

_DURATION_RE = re.compile(r"Duration:\s*(\d+):(\d{2}):(\d{2}(?:\.\d+)?)")
_VIDEO_SIZE_RE = re.compile(r"Video:.*?(\d{2,5})x(\d{2,5})")


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
    """打包后 ffmpeg 可能被放在 exe 同级、_internal/，或 onefile 的临时解压目录。"""
    dirs: list[Path] = []
    if getattr(sys, "frozen", False):
        exe_dir = Path(sys.executable).resolve().parent
        meipass = Path(getattr(sys, "_MEIPASS", exe_dir))
        dirs += [
            exe_dir / "ffmpeg",
            meipass / "ffmpeg",
            exe_dir,
            meipass,
            exe_dir / "resources",
            meipass / "resources",
            exe_dir / "_internal",
        ]
    here = Path(__file__).resolve()
    root = here.parents[3]
    dirs += [root / "resources" / "ffmpeg", root / "resources", here.parents[2] / "resources"]
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
    if not path.is_file():
        raise MediaError(f"文件不存在：{path}")

    ffmpeg = resolve_tool("ffmpeg", ffmpeg_dir)
    # 不带输出参数时 ffmpeg 会以 1 退出，但会把媒体信息打到 stderr，正是我们要的
    proc = _run([ffmpeg, "-hide_banner", "-nostdin", "-i", str(path)])
    info = proc.stderr or ""

    if "No such file or directory" in info or "Invalid data found" in info:
        raise MediaError("这个文件读不了，可能已损坏或不是音视频文件")

    match = _DURATION_RE.search(info)
    if not match:
        raise MediaError("读不到时长，文件可能已损坏或不是音视频文件")
    hours, minutes, seconds = match.groups()
    duration = int(hours) * 3600 + int(minutes) * 60 + float(seconds)
    if duration <= 0:
        raise MediaError("媒体时长为 0，无法转录")

    has_audio = "Audio:" in info
    size = _VIDEO_SIZE_RE.search(info)
    width = int(size.group(1)) if size else 0
    height = int(size.group(2)) if size else 0
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
