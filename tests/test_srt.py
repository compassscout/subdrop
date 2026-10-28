from pathlib import Path

import pytest

from subdrop.core.asr.base import Segment, normalize
from subdrop.core.srt import (
    format_timestamp,
    segments_to_srt,
    unique_output_path,
    write_subtitle,
)


@pytest.mark.parametrize(
    "seconds,expected",
    [
        (0, "00:00:00,000"),
        (1.5, "00:00:01,500"),
        (61.25, "00:01:01,250"),
        (3661.001, "01:01:01,001"),
        (-3, "00:00:00,000"),
    ],
)
def test_format_timestamp(seconds, expected):
    assert format_timestamp(seconds) == expected


def test_segments_to_srt_numbering_and_blank_lines():
    segs = [
        Segment(0.0, 1.2, "第一句"),
        Segment(1.3, 2.5, "第二句"),
    ]
    text = segments_to_srt(segs)
    assert text.startswith("1\n00:00:00,000 --> 00:00:01,200\n第一句")
    assert "2\n00:00:01,300 --> 00:00:02,500\n第二句" in text
    assert "\n\n" in text


def test_segments_to_srt_skips_blank_text():
    assert segments_to_srt([Segment(0, 1, "   ")]) == ""


def test_normalize_fixes_overlap_and_zero_length():
    segs = [Segment(0, 5, "a"), Segment(4, 4, "b"), Segment(6, 9, "  c  ")]
    out = normalize(segs)
    assert [s.text for s in out] == ["a", "b", "c"]
    assert out[0].end <= out[1].start
    assert out[1].end > out[1].start


def test_unique_output_path(tmp_path: Path):
    base = tmp_path / "video"
    first = unique_output_path(base)
    assert first.name == "video.srt"
    first.write_text("x", encoding="utf-8")
    second = unique_output_path(base)
    assert second.name == "video.1.srt"


def test_write_subtitle_formats(tmp_path: Path):
    segs = [Segment(0, 1, "hi")]
    srt = write_subtitle(tmp_path / "a.srt", segs, "srt")
    assert "-->" in srt.read_text(encoding="utf-8")
    vtt = write_subtitle(tmp_path / "a.vtt", segs, "vtt")
    assert vtt.read_text(encoding="utf-8").startswith("WEBVTT")
    txt = write_subtitle(tmp_path / "a.txt", segs, "txt")
    assert txt.read_text(encoding="utf-8").strip() == "hi"
