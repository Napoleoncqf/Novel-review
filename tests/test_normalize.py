"""测试数据规范化"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from novel_review.normalize import (
    normalize_string_list,
    normalize_deep_data,
    normalize_light_data,
    normalize_evidence_list,
)


def test_string_list_from_dicts():
    items = [
        {"name": "程朝", "behavior": "观察", "state": "矛盾"},
        {"name": "程夕", "state": "天真"},
        "普通字符串",
    ]
    result = normalize_string_list(items)
    assert len(result) == 3
    assert all(isinstance(r, str) for r in result)
    assert "程朝" in result[0]
    assert "程夕" in result[1]
    assert result[2] == "普通字符串"


def test_string_list_pure_strings():
    items = ["a", "b", "c"]
    result = normalize_string_list(items)
    assert result == ["a", "b", "c"]


def test_emotional_tone_list():
    data = {"emotional_tone": ["紧张", "压抑", "悲伤"]}
    result = normalize_deep_data(data)
    assert isinstance(result["emotional_tone"], str)
    assert "紧张" in result["emotional_tone"]


def test_emotional_tone_string():
    data = {"emotional_tone": "温馨"}
    result = normalize_deep_data(data)
    assert result["emotional_tone"] == "温馨"


def test_defect_id_extraction():
    data = {"defects_detected": ["D03感情线突兀", "D05", {"id": "D08伏笔断裂"}]}
    result = normalize_deep_data(data)
    assert result["defects_detected"] == ["D03", "D05", "D08"]


def test_defect_id_clean():
    data = {"defects_detected": ["D01", "D02", "D04"]}
    result = normalize_deep_data(data)
    assert result["defects_detected"] == ["D01", "D02", "D04"]


def test_evidence_normalization():
    items = [
        {"quote": "测试引用", "char_range": [100, 200], "chapter_ref": "第1章", "reason": "说明"},
        {"quote": "另一条" * 20, "char_range": "invalid"},  # 超长+无效range
    ]
    result = normalize_evidence_list(items)
    assert len(result) == 2
    assert result[0]["char_range"] == (100, 200)
    assert len(result[1]["quote"]) <= 60
    assert result[1]["char_range"] == (0, 0)


def test_light_data_pacing_clamp():
    data = {"pacing_score": 7.5}
    result = normalize_light_data(data)
    assert result["pacing_score"] == 5  # clamped to max

    data2 = {"pacing_score": -1}
    result2 = normalize_light_data(data2)
    assert result2["pacing_score"] == 1  # clamped to min


def test_light_data_pacing_string():
    data = {"pacing_score": "abc"}
    result = normalize_light_data(data)
    assert result["pacing_score"] == 3  # default
