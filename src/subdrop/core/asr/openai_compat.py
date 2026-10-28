"""OpenAI 兼容的语音转录接口（Groq / OpenAI / 硅基流动 / 自建都走这个）。

约定：POST {base_url}/audio/transcriptions，multipart 上传音频，
返回 verbose_json 里带 segments；如果服务商只给 text，就退回按标点均分。
"""

from __future__ import annotations

import time
from collections.abc import Callable
from pathlib import Path

import requests

from ..cues import text_to_segments
from .base import ASRError, Segment

RETRY_STATUS = {408, 409, 425, 429, 500, 502, 503, 504}


class OpenAICompatProvider:
    name = "openai_compat"

    def __init__(
        self,
        base_url: str,
        api_key: str,
        model: str,
        *,
        timeout: int = 600,
        max_retries: int = 3,
    ) -> None:
        self.base_url = (base_url or "").strip()
        self.api_key = (api_key or "").strip()
        self.model = (model or "").strip()
        self.timeout = timeout
        self.max_retries = max_retries
        if not self.base_url:
            raise ASRError("还没有填写接口地址（Base URL）")
        if not self.api_key:
            raise ASRError("还没有填写 API Key")
        if not self.model:
            raise ASRError("还没有填写模型名称")

    @property
    def endpoint(self) -> str:
        base = self.base_url.rstrip("/")
        if base.endswith("/audio/transcriptions"):
            return base
        if base.endswith("/v1"):
            return f"{base}/audio/transcriptions"
        return f"{base}/audio/transcriptions"

    def transcribe(
        self,
        audio: Path,
        *,
        language: str | None = None,
        should_cancel: Callable[[], bool] | None = None,
        duration: float | None = None,
    ) -> list[Segment]:
        data: dict[str, str] = {
            "model": self.model,
            "response_format": "verbose_json",
            "temperature": "0",
        }
        if language:
            data["language"] = language

        last_error: Exception | None = None
        for attempt in range(self.max_retries + 1):
            if should_cancel and should_cancel():
                raise ASRError("已取消")
            try:
                with audio.open("rb") as fh:
                    response = requests.post(
                        self.endpoint,
                        headers={"Authorization": f"Bearer {self.api_key}"},
                        files={"file": (audio.name, fh, "audio/mpeg")},
                        data=data,
                        timeout=(20, self.timeout),
                    )
            except requests.Timeout as exc:
                last_error = exc
                if attempt < self.max_retries:
                    time.sleep(2 * (attempt + 1))
                    continue
                raise ASRError("请求超时，网络可能不稳定，或该块音频太长") from exc
            except requests.RequestException as exc:
                last_error = exc
                if attempt < self.max_retries:
                    time.sleep(2 * (attempt + 1))
                    continue
                raise ASRError(f"网络请求失败：{exc}") from exc

            if response.status_code in RETRY_STATUS and attempt < self.max_retries:
                wait = float(response.headers.get("Retry-After") or 2 * (attempt + 1))
                time.sleep(min(wait, 30))
                continue
            if response.status_code >= 400:
                raise ASRError(_friendly_error(response))
            return self._parse(response.json(), language, duration)

        raise ASRError(f"多次重试后仍然失败：{last_error}")

    def _parse(
        self, payload: dict, language: str | None, duration: float | None
    ) -> list[Segment]:
        raw_segments = payload.get("segments") or []
        segments: list[Segment] = []
        for item in raw_segments:
            if not isinstance(item, dict):
                continue
            text = str(item.get("text") or "").strip()
            if not text:
                continue
            try:
                segments.append(
                    Segment(float(item.get("start") or 0.0), float(item.get("end") or 0.0), text)
                )
            except (TypeError, ValueError):
                continue
        if segments:
            return segments

        words = payload.get("words") or []
        if words:
            built: list[Segment] = []
            buf: list[dict] = []
            for word in words:
                buf.append(word)
                if str(word.get("word", "")).strip().endswith(tuple("。！？!?，,；;")):
                    built.append(_words_to_segment(buf))
                    buf = []
            if buf:
                built.append(_words_to_segment(buf))
            if built:
                return built

        text = str(payload.get("text") or payload.get("transcription") or "").strip()
        if not text:
            raise ASRError("接口返回里没有识别文本，请确认模型名与接口地址是否匹配")
        total = float(payload.get("duration") or duration or 0.0)
        if total <= 0:
            raise ASRError("接口没有返回时间戳，也拿不到音频时长，无法生成字幕")
        return text_to_segments(text, total, language)


def _words_to_segment(words: list[dict]) -> Segment:
    start = float(words[0].get("start") or 0.0)
    end = float(words[-1].get("end") or start)
    text = "".join(str(w.get("word") or "") for w in words).strip()
    return Segment(start, end, text)


def _friendly_error(response: requests.Response) -> str:
    detail = ""
    try:
        payload = response.json()
        detail = (
            payload.get("error", {}).get("message")
            if isinstance(payload.get("error"), dict)
            else payload.get("message") or payload.get("detail") or ""
        )
    except ValueError:
        detail = (response.text or "")[:300]
    detail = detail.strip() if isinstance(detail, str) else str(detail)

    if response.status_code == 401:
        return f"API Key 无效或已过期（401）。{detail}"
    if response.status_code == 403:
        return f"没有访问权限（403），可能是 Key 未开通该模型。{detail}"
    if response.status_code == 404:
        return f"接口地址不对（404），检查 Base URL 是否包含 /v1。{detail}"
    if response.status_code == 413:
        return "音频块太大被拒绝（413），把「分块时长」调小一些。"
    if response.status_code == 429:
        return f"请求太频繁或额度用尽（429）。{detail}"
    return f"接口返回 {response.status_code}：{detail[:300]}"
