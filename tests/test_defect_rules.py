"""测试缺陷检测引擎"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from novel_review.models import LightResult, DeepResult, CrossChunkAnalysis, ForeshadowingPair
from novel_review.defect_rules import run_defect_detection


def _make_light(cid, pacing=3, progression="yes: ok", flags=None):
    return LightResult(
        chunk_id=cid,
        char_range=(cid * 1000, (cid + 1) * 1000),
        pacing_score=pacing,
        plot_progression=progression,
        candidate_flags=flags or [],
    )


def _make_deep(cid, density=3, defects=None, tone="平静"):
    return DeepResult(
        chunk_id=cid,
        char_range=(cid * 1000, (cid + 1) * 1000),
        information_density=density,
        defects_detected=defects or [],
        emotional_tone=tone,
    )


def test_d04_pacing_collapse():
    """连续3块低节奏+无推进 → D04"""
    lights = [
        _make_light(0, pacing=4, progression="yes: ok"),
        _make_light(1, pacing=1, progression="no: 无推进"),
        _make_light(2, pacing=2, progression="no: 无推进"),
        _make_light(3, pacing=1, progression="no: 无推进"),
        _make_light(4, pacing=4, progression="yes: ok"),
    ]
    deeps = [_make_deep(i) for i in range(5)]
    analysis = CrossChunkAnalysis(pacing_curve=[4, 1, 2, 1, 4])

    defects = run_defect_detection(lights, deeps, analysis)
    d04 = [d for d in defects if d.rule_id == "D04"]
    assert len(d04) == 1
    assert set([1, 2, 3]).issubset(set(int(x) for x in d04[0].location.replace("块", "").split("、")))


def test_d04_no_collapse():
    """非连续低节奏 → 不触发"""
    lights = [
        _make_light(0, pacing=1, progression="no: x"),
        _make_light(1, pacing=4, progression="yes: ok"),  # 中断
        _make_light(2, pacing=1, progression="no: x"),
        _make_light(3, pacing=4, progression="yes: ok"),
    ]
    deeps = [_make_deep(i) for i in range(4)]
    analysis = CrossChunkAnalysis(pacing_curve=[1, 4, 1, 4])

    defects = run_defect_detection(lights, deeps, analysis)
    d04 = [d for d in defects if d.rule_id == "D04"]
    assert len(d04) == 0


def test_d07_padding():
    """连续2块低密度 → D07"""
    lights = [_make_light(i) for i in range(5)]
    deeps = [
        _make_deep(0, density=4),
        _make_deep(1, density=1),
        _make_deep(2, density=2),
        _make_deep(3, density=4),
        _make_deep(4, density=4),
    ]
    analysis = CrossChunkAnalysis(pacing_curve=[3] * 5)

    defects = run_defect_detection(lights, deeps, analysis)
    d07 = [d for d in defects if d.rule_id == "D07"]
    assert len(d07) == 1


def test_d08_broken_foreshadowing():
    """伏笔5块后仍未回收 → D08"""
    lights = [_make_light(i) for i in range(10)]
    deeps = [_make_deep(i) for i in range(10)]
    analysis = CrossChunkAnalysis(
        pacing_curve=[3] * 10,
        foreshadowing_pairs=[
            ForeshadowingPair(description="暗示", planted_chunk=2, status="open"),
            ForeshadowingPair(description="伏笔B", planted_chunk=0, resolved_chunk=3, status="resolved"),
        ],
    )

    defects = run_defect_detection(lights, deeps, analysis)
    d08 = [d for d in defects if d.rule_id == "D08"]
    assert len(d08) == 1


def test_llm_defects_passthrough():
    """LLM标注的D03/D05应透传"""
    lights = [_make_light(i) for i in range(3)]
    deeps = [
        _make_deep(0, defects=["D03"]),
        _make_deep(1, defects=["D03", "D05"]),
        _make_deep(2),
    ]
    analysis = CrossChunkAnalysis(pacing_curve=[3] * 3)

    defects = run_defect_detection(lights, deeps, analysis)
    d03 = [d for d in defects if d.rule_id == "D03"]
    d05 = [d for d in defects if d.rule_id == "D05"]
    assert len(d03) == 1
    assert len(d05) == 1


def test_merge_duplicate_rules():
    """启发式+LLM同时检测到D04应合并"""
    lights = [
        _make_light(0, pacing=1, progression="no: x"),
        _make_light(1, pacing=1, progression="no: x"),
        _make_light(2, pacing=1, progression="no: x"),
    ]
    deeps = [
        _make_deep(0, defects=["D04"]),
        _make_deep(1),
        _make_deep(2),
    ]
    analysis = CrossChunkAnalysis(pacing_curve=[1, 1, 1])

    defects = run_defect_detection(lights, deeps, analysis)
    d04 = [d for d in defects if d.rule_id == "D04"]
    assert len(d04) == 1  # 合并而非重复
