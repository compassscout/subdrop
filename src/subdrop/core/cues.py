"""字幕断句与跨块拼接。

两个容易被忽略、却直接决定"能不能用"的细节：

1. 有些云 ASR（如 SenseVoice）只返回整段文本，没有时间戳。
   那就按标点切句，再按字数比例分配时间 —— 精度不如原生时间戳，但至少能用。
2. 视频被切成 10 分钟一块送去识别，句子会正好断在接缝处。
   这里把接缝两侧的残句重新粘成一句，避免字幕里出现半句话。
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from .asr.base import Segment

# 句末标点（中英混排都要照顾）
SENTENCE_END = "。！？!?；;…\n"
# 句中标点，切长句时用
CLAUSE_END = "，,、：:）)】」》"

_CJK = re.compile(r"[\u3400-\u9fff\u3040-\u30ff\uac00-\ud7af]")
_SPEAKERS = re.compile(r"^\s*\[?([A-Z][A-Za-z .'-]{0,20})\]?\s*[:：]\s*")


def char_weight(text: str) -> float:
    """中文一个字算 1，拉丁字符按 0.5 折算，避免中英混排时长严重失衡。"""
    cjk = len(_CJK.findall(text))
    other = max(0, len(re.sub(r"\s", "", text)) - cjk)
    return cjk + other * 0.5


def max_chars_for(language: str | None) -> int:
    if language in ("zh", "ja", "ko", "yue"):
        return 34
    if language is None:
        return 52
    return 84


def split_sentences(text: str) -> list[str]:
    text = re.sub(r"[ \t]+", " ", text.replace("\r", "\n")).strip()
    if not text:
        return []
    parts: list[str] = []
    buf = ""
    for ch in text:
        buf += ch
        if ch in SENTENCE_END:
            if buf.strip():
                parts.append(buf.strip())
            buf = ""
    if buf.strip():
        parts.append(buf.strip())
    return parts


def _split_long(sentence: str, limit: int) -> list[str]:
    if char_weight(sentence) <= limit:
        return [sentence]
    pieces: list[str] = []
    buf = ""
    for ch in sentence:
        buf += ch
        if ch in CLAUSE_END or char_weight(buf) >= limit * 0.85:
            pieces.append(buf.strip())
            buf = ""
    if buf.strip():
        pieces.append(buf.strip())
    # 仍超长就硬切
    out: list[str] = []
    for piece in pieces:
        while char_weight(piece) > limit * 1.3 and len(piece) > limit:
            out.append(piece[:limit])
            piece = piece[limit:]
        if piece:
            out.append(piece)
    return out


def text_to_segments(text: str, duration: float, language: str | None = "zh") -> list[Segment]:
    """没有时间戳时的兜底：按标点切句，按字数比例分配时间。"""
    limit = max_chars_for(language)
    sentences: list[str] = []
    for s in split_sentences(text):
        sentences.extend(_split_long(s, limit))
    sentences = [s for s in sentences if s.strip()]
    if not sentences:
        return []

    weights = [max(1.0, char_weight(s)) for s in sentences]
    total = sum(weights)
    cursor = 0.0
    segments: list[Segment] = []
    for sentence, weight in zip(sentences, weights, strict=True):
        span = duration * weight / total if duration > 0 else 3.0
        start = cursor
        end = min(duration, cursor + span) if duration > 0 else cursor + span
        segments.append(Segment(round(start, 3), round(end, 3), sentence))
        cursor = end
    return segments


@dataclass(slots=True)
class ChunkResult:
    offset: float
    duration: float
    segments: list[Segment]


def join_chunks(chunks: list[ChunkResult], tolerance: float = 2.0) -> list[Segment]:
    """把各块的识别结果按偏移拼起来，并修复接缝处的断句。"""
    merged: list[Segment] = []
    for chunk in chunks:
        shifted = [s.shifted(chunk.offset) for s in chunk.segments]
        if not shifted:
            continue
        if merged and chunk.offset > 0:
            prev = merged[-1]
            first = shifted[0]
            boundary = chunk.offset
            local_start = first.start - boundary
            local_prev_end = prev.end - boundary
            # 上一块结尾贴着接缝 + 本块开头贴着 0 → 同一句话被切开了
            if prev.end >= boundary - tolerance and local_start <= tolerance:
                same = prev.text.strip() == first.text.strip()
                if same:
                    prev.end = max(prev.end, first.end)
                    shifted = shifted[1:]
                elif local_start < local_prev_end + 1.5:
                    merged[-1] = Segment(
                        prev.start,
                        max(first.end, prev.end),
                        f"{prev.text.rstrip()}{first.text.lstrip()}",
                    )
                    shifted = shifted[1:]
        merged.extend(shifted)
    return merged
