"""测试文本预处理与分块"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from novel_review.preprocessor import find_chapter_breaks, build_chunks, read_text, file_sha256


def test_chapter_detection_numbered():
    text = "前言内容\n第1章 出生\n正文内容\n第2章 成长\n更多内容\n第3章 结局\n结局内容"
    breaks = find_chapter_breaks(text)
    assert len(breaks) == 3
    assert breaks[0][1] == "第1章 出生"
    assert breaks[1][1] == "第2章 成长"
    assert breaks[2][1] == "第3章 结局"


def test_chapter_detection_chinese_numbers():
    text = "第一章 开始\n内容\n第二章 发展\n内容\n第三章 高潮\n内容"
    breaks = find_chapter_breaks(text)
    assert len(breaks) == 3


def test_chapter_detection_none():
    text = "这是一段没有章节标记的短文。" * 100
    breaks = find_chapter_breaks(text)
    assert len(breaks) == 0


def test_build_chunks_with_chapters():
    chapters = "\n".join([f"第{i}章 标题{i}\n" + "内容" * 500 for i in range(1, 6)])
    text = "前言简介\n" + chapters
    path = Path("test.txt")
    manifest = build_chunks(text, path)
    assert manifest.total_chunks >= 5
    assert manifest.total_chars == len(text)
    assert manifest.source_file_sha256 == file_sha256(text)
    # 每块都有文本
    for chunk in manifest.chunks:
        assert len(chunk.text) > 0
        assert chunk.char_range[1] > chunk.char_range[0]


def test_build_chunks_no_chapters():
    text = "这是一段很长的文本。" * 2000  # 约2万字
    path = Path("test.txt")
    manifest = build_chunks(text, path)
    assert manifest.total_chunks >= 2
    for chunk in manifest.chunks:
        assert len(chunk.text) <= 8000  # 不超过chunk_size + 断句余量


def test_build_chunks_short_text():
    text = "短文本。"
    path = Path("test.txt")
    manifest = build_chunks(text, path)
    assert manifest.total_chunks == 1


def test_sha256_deterministic():
    text = "测试文本"
    assert file_sha256(text) == file_sha256(text)
    assert file_sha256(text) != file_sha256("不同文本")


def test_real_file():
    """测试真实小说文件（如果存在）"""
    data_dir = Path(__file__).parent.parent / "data"
    test_file = data_dir / "朝夕（精校版）.txt"
    if not test_file.exists():
        return  # 跳过
    text = read_text(test_file)
    assert len(text) > 100000
    manifest = build_chunks(text, test_file)
    assert manifest.total_chunks > 10
    # 检查章节识别
    has_chapter = any(c.chapter_ref and "章" in c.chapter_ref for c in manifest.chunks)
    assert has_chapter, "应该能识别到章节标记"
