"""用户设置：纯 JSON，存在 %APPDATA%/SubDrop/settings.json。"""

from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass, fields
from pathlib import Path

from . import APP_NAME


def config_dir() -> Path:
    base = os.environ.get("APPDATA") or os.environ.get("XDG_CONFIG_HOME")
    root = Path(base) if base else Path.home() / ".config"
    path = root / APP_NAME
    path.mkdir(parents=True, exist_ok=True)
    return path


def cache_dir() -> Path:
    base = os.environ.get("LOCALAPPDATA") or os.environ.get("XDG_CACHE_HOME")
    root = Path(base) if base else Path.home() / ".cache"
    path = root / APP_NAME / "cache"
    path.mkdir(parents=True, exist_ok=True)
    return path


CONFIG_PATH = config_dir() / "settings.json"


PROVIDER_PRESETS: dict[str, dict[str, str]] = {
    "groq": {
        "label": "Groq（免费额度，推荐）",
        "base_url": "https://api.groq.com/openai/v1",
        "model": "whisper-large-v3-turbo",
        "signup": "https://console.groq.com/keys",
    },
    "openai": {
        "label": "OpenAI",
        "base_url": "https://api.openai.com/v1",
        "model": "whisper-1",
        "signup": "https://platform.openai.com/api-keys",
    },
    "siliconflow": {
        "label": "硅基流动（国内可直连）",
        "base_url": "https://api.siliconflow.cn/v1",
        "model": "FunAudioLLM/SenseVoiceSmall",
        "signup": "https://cloud.siliconflow.cn/account/ak",
    },
    "custom": {
        "label": "自定义（任意 OpenAI 兼容接口）",
        "base_url": "",
        "model": "",
        "signup": "",
    },
}

LANGUAGES: list[tuple[str, str]] = [
    ("auto", "自动识别"),
    ("zh", "中文"),
    ("en", "英语"),
    ("ja", "日语"),
    ("ko", "韩语"),
    ("yue", "粤语"),
    ("de", "德语"),
    ("fr", "法语"),
    ("es", "西班牙语"),
    ("ru", "俄语"),
]


@dataclass
class Settings:
    provider: str = "groq"
    base_url: str = PROVIDER_PRESETS["groq"]["base_url"]
    api_key: str = ""
    model: str = PROVIDER_PRESETS["groq"]["model"]
    language: str = "zh"
    chunk_seconds: int = 600
    output_format: str = "srt"
    ffmpeg_dir: str = ""
    keep_audio: bool = False
    theme: str = "light"

    @property
    def language_value(self) -> str | None:
        return None if self.language in ("", "auto") else self.language

    def save(self, path: Path | None = None) -> None:
        target = path or CONFIG_PATH
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(
            json.dumps(asdict(self), ensure_ascii=False, indent=2), encoding="utf-8"
        )

    @classmethod
    def load(cls, path: Path | None = None) -> Settings:
        target = path or CONFIG_PATH
        if not target.exists():
            return cls()
        try:
            raw = json.loads(target.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return cls()
        known = {f.name for f in fields(cls)}
        return cls(**{k: v for k, v in raw.items() if k in known})

    def apply_preset(self, key: str) -> None:
        preset = PROVIDER_PRESETS.get(key)
        if not preset:
            return
        self.provider = key
        if preset["base_url"]:
            self.base_url = preset["base_url"]
        if preset["model"]:
            self.model = preset["model"]
