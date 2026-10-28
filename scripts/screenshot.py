"""生成 README 用的界面截图。

用法：uv run python scripts/screenshot.py
输出：docs/screenshot.png、docs/screenshot-settings.png

会用 ffmpeg 造一个 12 秒的假视频，让界面处于「已选中文件」的状态。
"""

from __future__ import annotations

import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from PySide6.QtWidgets import QApplication  # noqa: E402

from subdrop.app import _load_stylesheet  # noqa: E402
from subdrop.config import Settings  # noqa: E402
from subdrop.ui.main_window import MainWindow  # noqa: E402


def _make_sample(tmp: Path) -> Path | None:
    if not shutil.which("ffmpeg"):
        return None
    target = tmp / "第 3 讲 · 如何做出第一个产品.mp4"
    cmd = [
        "ffmpeg", "-hide_banner", "-nostdin", "-y",
        "-f", "lavfi", "-i", "color=c=0x101828:s=1280x720:d=12",
        "-f", "lavfi", "-i", "sine=frequency=440:duration=12",
        "-shortest", "-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p",
        "-c:a", "aac", "-b:a", "64k", str(target),
    ]
    try:
        subprocess.run(cmd, check=True, capture_output=True)
    except subprocess.CalledProcessError:
        return None
    return target


def main() -> int:
    app = QApplication(sys.argv)
    _load_stylesheet(app)

    settings = Settings(provider="groq", language="zh")
    window = MainWindow(settings)
    window.resize(1060, 730)
    window.show()
    app.processEvents()

    out = ROOT / "docs"
    out.mkdir(exist_ok=True)

    with tempfile.TemporaryDirectory() as tmpdir:
        sample = _make_sample(Path(tmpdir))
        if sample:
            window.transcribe_page.load_file(str(sample))
            app.processEvents()
        window.grab().save(str(out / "screenshot.png"))

    window._select(4)
    app.processEvents()
    window.grab().save(str(out / "screenshot-settings.png"))
    print("saved screenshots to", out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
