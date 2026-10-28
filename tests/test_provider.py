
import pytest

from subdrop.core.asr.base import ASRError
from subdrop.core.asr.openai_compat import OpenAICompatProvider


class FakeResponse:
    def __init__(self, status_code=200, payload=None, headers=None, text=""):
        self.status_code = status_code
        self._payload = payload or {}
        self.headers = headers or {}
        self.text = text

    def json(self):
        if self._payload is None:
            raise ValueError("no json")
        return self._payload


def _provider(**kwargs):
    return OpenAICompatProvider("https://api.example.com/v1", "sk-test", "whisper-1", **kwargs)


def test_endpoint_normalization():
    assert _provider().endpoint == "https://api.example.com/v1/audio/transcriptions"
    p = OpenAICompatProvider("https://api.example.com/v1/audio/transcriptions", "k", "m")
    assert p.endpoint == "https://api.example.com/v1/audio/transcriptions"
    p2 = OpenAICompatProvider("https://api.example.com/openai", "k", "m")
    assert p2.endpoint == "https://api.example.com/openai/audio/transcriptions"


def test_requires_key():
    with pytest.raises(ASRError):
        OpenAICompatProvider("https://x/v1", "", "m")


def test_parse_segments(monkeypatch, tmp_path):
    audio = tmp_path / "a.mp3"
    audio.write_bytes(b"fake")

    def fake_post(*args, **kwargs):
        return FakeResponse(
            payload={
                "segments": [
                    {"start": 0.0, "end": 1.5, "text": "你好"},
                    {"start": 1.5, "end": 3.0, "text": "世界"},
                ],
                "text": "你好世界",
            }
        )

    monkeypatch.setattr("requests.post", fake_post)
    segs = _provider().transcribe(audio, language="zh", duration=3.0)
    assert [s.text for s in segs] == ["你好", "世界"]
    assert segs[1].end == 3.0


def test_text_only_fallback(monkeypatch, tmp_path):
    audio = tmp_path / "a.mp3"
    audio.write_bytes(b"fake")

    _provider  # keep reference for lint

    def fake_post(*args, **kwargs):
        return FakeResponse(payload={"text": "第一句。第二句。", "duration": 10.0})

    monkeypatch.setattr("requests.post", fake_post)
    segs = _provider().transcribe(audio, language="zh", duration=10.0)
    assert len(segs) == 2
    assert abs(segs[-1].end - 10.0) < 0.01


def test_401_is_friendly(monkeypatch, tmp_path):
    audio = tmp_path / "a.mp3"
    audio.write_bytes(b"fake")
    monkeypatch.setattr(
        "requests.post",
        lambda *a, **k: FakeResponse(status_code=401, payload={"error": {"message": "bad key"}}),
    )
    with pytest.raises(ASRError) as exc:
        _provider(max_retries=0).transcribe(audio)
    assert "API Key" in str(exc.value)


def test_missing_duration_and_text_raises(monkeypatch, tmp_path):
    audio = tmp_path / "a.mp3"
    audio.write_bytes(b"fake")
    monkeypatch.setattr("requests.post", lambda *a, **k: FakeResponse(payload={"text": "hi"}))
    with pytest.raises(ASRError):
        _provider(max_retries=0).transcribe(audio, duration=None)
