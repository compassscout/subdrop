"""ASR 后端工厂：界面里换后端只改这里。"""

from __future__ import annotations

from ...config import Settings
from .mock import MockProvider
from .openai_compat import OpenAICompatProvider


def build_provider(settings: Settings):
    if settings.provider == "mock":
        return MockProvider()
    return OpenAICompatProvider(
        base_url=settings.base_url,
        api_key=settings.api_key,
        model=settings.model,
    )
