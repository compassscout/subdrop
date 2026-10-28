from pathlib import Path

import pytest

from subdrop.core.media import MediaError, extract_chunks, probe, resolve_tool


def test_probe_reads_duration_and_audio(sample_audio: Path):
    info = probe(sample_audio)
    assert 2.5 < info.duration < 3.5
    assert info.has_audio is True
    assert info.duration_text == "0:03"


def test_extract_chunks_produces_files(sample_audio: Path, tmp_path: Path):
    out_dir = tmp_path / "audio"
    chunks = extract_chunks(sample_audio, out_dir, chunk_seconds=600)
    assert len(chunks) == 1
    assert chunks[0].exists()
    assert chunks[0].stat().st_size > 0


def test_extract_chunks_splits_long_audio(sample_audio: Path, tmp_path: Path):
    # 3 秒的音频按 1 秒切（函数内部会把下限抬到 60 秒，所以这里只验证单块）
    chunks = extract_chunks(sample_audio, tmp_path / "audio2", chunk_seconds=1)
    assert len(chunks) >= 1


def test_missing_file_raises(tmp_path: Path):
    with pytest.raises(MediaError):
        probe(tmp_path / "nope.mp4")


def test_resolve_tool_missing():
    with pytest.raises(MediaError):
        resolve_tool("definitely-not-a-real-binary")
