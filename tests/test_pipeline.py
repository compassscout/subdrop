from pathlib import Path

from subdrop.config import Settings
from subdrop.core.asr.mock import MockProvider
from subdrop.core.pipeline import TranscribeJob


def _settings(tmp_path: Path) -> Settings:
    return Settings(
        provider="mock",
        language="zh",
        chunk_seconds=60,
        output_format="srt",
        keep_audio=False,
    )


def test_pipeline_end_to_end(sample_audio: Path, tmp_path: Path):
    job = TranscribeJob(
        sample_audio,
        _settings(tmp_path),
        MockProvider(),
        work_root=tmp_path / "work",
    )
    events: list[tuple[float, str]] = []
    result = job.run(on_progress=lambda p, m: events.append((p, m)))

    assert result.output.exists()
    assert result.output.suffix == ".srt"
    assert len(result.segments) == 4
    assert result.output.read_text(encoding="utf-8").startswith("1\n")
    assert events[-1][0] == 1.0
    assert result.elapsed > 0


def test_pipeline_reuses_cached_chunks(sample_audio: Path, tmp_path: Path):
    settings = _settings(tmp_path)
    work = tmp_path / "work"
    first = TranscribeJob(sample_audio, settings, MockProvider(), work_root=work).run()
    second = TranscribeJob(sample_audio, settings, MockProvider(), work_root=work).run()
    assert first.reused_chunks == 0
    assert second.reused_chunks == 1
    assert second.output != first.output  # 不覆盖已有字幕


def test_pipeline_does_not_overwrite_output(sample_audio: Path, tmp_path: Path):
    settings = _settings(tmp_path)
    work = tmp_path / "work"
    TranscribeJob(sample_audio, settings, MockProvider(), work_root=work).run()
    result = TranscribeJob(sample_audio, settings, MockProvider(), work_root=work).run()
    assert result.output.name == "sample.1.srt"


def test_pipeline_cancel(sample_audio: Path, tmp_path: Path):
    job = TranscribeJob(
        sample_audio, _settings(tmp_path), MockProvider(), work_root=tmp_path / "work"
    )
    job.cancel()
    try:
        job.run()
    except Exception as exc:  # noqa: BLE001
        assert "取消" in str(exc)
    else:
        raise AssertionError("取消后应当抛异常")
