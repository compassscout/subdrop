from subdrop.core.asr.base import Segment
from subdrop.core.cues import (
    ChunkResult,
    char_weight,
    join_chunks,
    split_sentences,
    text_to_segments,
)


def test_split_sentences_keeps_punctuation():
    assert split_sentences("你好。今天天气不错！走吗？") == [
        "你好。",
        "今天天气不错！",
        "走吗？",
    ]


def test_char_weight_counts_cjk_more():
    assert char_weight("你好") == 2
    assert char_weight("hello") == 2.5


def test_text_to_segments_covers_duration():
    text = "第一句话。第二句话。第三句话。"
    segs = text_to_segments(text, 30.0, "zh")
    assert len(segs) == 3
    assert segs[0].start == 0
    assert abs(segs[-1].end - 30.0) < 0.01
    for a, b in zip(segs, segs[1:], strict=False):
        assert a.end == b.start


def test_text_to_segments_splits_long_sentence():
    text = "啊" * 200
    segs = text_to_segments(text, 60.0, "zh")
    assert len(segs) > 1
    assert all(len(s.text) <= 60 for s in segs)


def test_join_chunks_merges_cut_sentence():
    chunk1 = ChunkResult(0.0, 600.0, [Segment(590.0, 600.0, "上半句")])
    chunk2 = ChunkResult(600.0, 600.0, [Segment(0.0, 3.0, "下半句。"), Segment(4.0, 8.0, "下一句。")])
    out = join_chunks([chunk1, chunk2])
    assert out[0].text == "上半句下半句。"
    assert len(out) == 2
    assert out[1].text == "下一句。"


def test_join_chunks_dedupes_repeated_text():
    chunk1 = ChunkResult(0.0, 600.0, [Segment(595.0, 600.0, "重复")])
    chunk2 = ChunkResult(600.0, 600.0, [Segment(0.0, 2.0, "重复")])
    out = join_chunks([chunk1, chunk2])
    assert len(out) == 1


def test_join_chunks_keeps_far_apart_segments():
    chunk1 = ChunkResult(0.0, 600.0, [Segment(10.0, 12.0, "a")])
    chunk2 = ChunkResult(600.0, 600.0, [Segment(0.0, 2.0, "b")])
    out = join_chunks([chunk1, chunk2])
    assert [s.text for s in out] == ["a", "b"]
