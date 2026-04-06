"""T04: 文本预处理 — 编码检测、章节识别、分块"""
from __future__ import annotations
import hashlib
import re
from pathlib import Path

from charset_normalizer import from_path

from .models import ChunkInfo, ChunkManifest

CHAPTER_PATTERNS = [
    re.compile(r"^第[一二三四五六七八九十百千零\d]+章\s*.*$", re.MULTILINE),
    re.compile(r"^Chapter\s*\d+", re.MULTILINE | re.IGNORECASE),
    re.compile(r"^\s*第[一二三四五六七八九十百千零\d]+节", re.MULTILINE),
]

DEFAULT_CHUNK_SIZE = 6000
OVERLAP = 500


def read_text(path: Path) -> str:
    raw = path.read_bytes()
    # 先尝试UTF-8
    try:
        return raw.decode("utf-8")
    except UnicodeDecodeError:
        pass
    # charset_normalizer自动检测
    result = from_path(path)
    best = result.best()
    if best is None:
        raise ValueError(f"无法检测文件编码: {path}")
    return str(best)


def file_sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


def find_chapter_breaks(text: str) -> list[tuple[int, str]]:
    """返回 [(char_offset, chapter_title), ...]"""
    breaks = []
    for pat in CHAPTER_PATTERNS:
        for m in pat.finditer(text):
            breaks.append((m.start(), m.group().strip()))
    breaks.sort(key=lambda x: x[0])
    # 去重（多个pattern可能匹配同一位置）
    seen = set()
    unique = []
    for offset, title in breaks:
        if offset not in seen:
            seen.add(offset)
            unique.append((offset, title))
    return unique


def build_chunks(text: str, source_path: Path) -> ChunkManifest:
    sha = file_sha256(text)
    chapters = find_chapter_breaks(text)

    chunks: list[ChunkInfo] = []

    if chapters and len(chapters) >= 3:
        # 按章节切分
        for i, (offset, title) in enumerate(chapters):
            end = chapters[i + 1][0] if i + 1 < len(chapters) else len(text)
            segment = text[offset:end]
            # 如果单章过长，再按固定大小切分
            if len(segment) > DEFAULT_CHUNK_SIZE * 2:
                sub_chunks = _fixed_split(segment, offset, title)
                chunks.extend(sub_chunks)
            else:
                chunks.append(ChunkInfo(
                    chunk_id=0,  # 后面重编号
                    char_range=(offset, end),
                    chapter_ref=title,
                    text=segment,
                ))
        # 开头在第一章之前的文本（简介等）
        if chapters[0][0] > 200:
            chunks.insert(0, ChunkInfo(
                chunk_id=0,
                char_range=(0, chapters[0][0]),
                chapter_ref="前言/简介",
                text=text[:chapters[0][0]],
            ))
    else:
        # 无章节标记，按固定大小切分
        chunks = _fixed_split(text, 0, "")

    # 重编号
    for i, c in enumerate(chunks):
        c.chunk_id = i

    return ChunkManifest(
        source_file=str(source_path),
        source_file_sha256=sha,
        total_chars=len(text),
        total_chunks=len(chunks),
        chunks=chunks,
    )


def _fixed_split(text: str, base_offset: int, chapter_ref: str) -> list[ChunkInfo]:
    chunks = []
    pos = 0
    while pos < len(text):
        end = min(pos + DEFAULT_CHUNK_SIZE, len(text))
        # 尽量在句号/换行处断开
        if end < len(text):
            for sep in ["\n\n", "\n", "。", "！", "？"]:
                idx = text.rfind(sep, pos + DEFAULT_CHUNK_SIZE // 2, end + 500)
                if idx > pos:
                    end = idx + len(sep)
                    break
        chunks.append(ChunkInfo(
            chunk_id=0,
            char_range=(base_offset + pos, base_offset + end),
            chapter_ref=chapter_ref,
            text=text[pos:end],
        ))
        pos = end
    return chunks
