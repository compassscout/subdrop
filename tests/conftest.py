import shutil
import subprocess
from pathlib import Path

import pytest


@pytest.fixture(scope="session")
def ffmpeg_available() -> bool:
    return bool(shutil.which("ffmpeg") and shutil.which("ffprobe"))


@pytest.fixture
def sample_audio(tmp_path: Path, ffmpeg_available: bool) -> Path:
    if not ffmpeg_available:
        pytest.skip("需要 ffmpeg")
    target = tmp_path / "sample.mp3"
    subprocess.run(
        [
            "ffmpeg", "-hide_banner", "-nostdin", "-y",
            "-f", "lavfi", "-i", "sine=frequency=440:duration=3",
            "-ac", "1", "-ar", "16000", "-b:a", "32k",
            str(target),
        ],
        check=True,
        capture_output=True,
    )
    return target
