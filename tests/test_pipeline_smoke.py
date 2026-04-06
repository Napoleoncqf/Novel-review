"""烟雾测试：验证已生成产物的schema和数据完整性"""
import sys
import json
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from novel_review.models import (
    ChunkManifest, LightResult, DeepResult,
    CrossChunkAnalysis, FinalReport,
)

ARTIFACTS = Path(__file__).parent.parent / "artifacts"
OUTPUT = Path(__file__).parent.parent / "output"


def _load(path: Path) -> dict:
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def test_manifest_schema():
    """chunks.json通过ChunkManifest schema校验"""
    fp = ARTIFACTS / "chunks.json"
    if not fp.exists():
        return
    data = _load(fp)
    manifest = ChunkManifest(**data)
    assert manifest.total_chunks > 0
    assert manifest.total_chars > 0
    assert len(manifest.chunks) == manifest.total_chunks


def test_light_results_schema():
    """所有phase1_light产物通过LightResult校验"""
    d = ARTIFACTS / "phase1_light"
    if not d.exists():
        return
    fail_count = 0
    total = 0
    for fp in sorted(d.glob("chunk_*.json")):
        total += 1
        data = _load(fp)
        try:
            lr = LightResult(**data)
            assert lr.pacing_score >= 1
            assert lr.pacing_score <= 5
        except Exception:
            fail_count += 1
    assert total > 0, "应该有light结果文件"
    assert fail_count == 0, f"{fail_count}/{total}个light结果schema校验失败"


def test_deep_results_schema():
    """所有phase1_deep产物通过DeepResult校验"""
    d = ARTIFACTS / "phase1_deep"
    if not d.exists():
        return
    fail_count = 0
    error_chunks = []
    total = 0
    for fp in sorted(d.glob("chunk_*.json")):
        total += 1
        data = _load(fp)
        try:
            dr = DeepResult(**data)
            # 检查是否有解析失败标记
            if any("[解析失败" in str(e) for e in dr.plot_events):
                error_chunks.append(fp.stem)
        except Exception as e:
            fail_count += 1
            error_chunks.append(f"{fp.stem}: {e}")
    assert total > 0, "应该有deep结果文件"
    assert fail_count == 0, f"{fail_count}/{total}个deep结果schema校验失败: {error_chunks}"
    assert len(error_chunks) == 0, f"解析失败块: {error_chunks}"


def test_cross_chunk_schema():
    """cross_chunk_analysis.json通过CrossChunkAnalysis校验"""
    fp = ARTIFACTS / "phase2" / "cross_chunk_analysis.json"
    if not fp.exists():
        return
    data = _load(fp)
    analysis = CrossChunkAnalysis(**data)
    assert len(analysis.pacing_curve) > 0
    assert len(analysis.character_arcs) > 0
    assert analysis.coverage.get("total_chunks", 0) > 0


def test_evidence_index():
    """evidence_index.json有足够的证据条目"""
    fp = ARTIFACTS / "phase2" / "evidence_index.json"
    if not fp.exists():
        return
    data = _load(fp)
    assert isinstance(data, list)
    assert len(data) >= 10, f"证据太少: {len(data)}条"
    # 每条都有quote
    for item in data[:20]:
        assert "quote" in item and item["quote"], f"缺少quote: {item}"


def test_final_report_schema():
    """report.json通过FinalReport校验"""
    fp = OUTPUT / "report.json"
    if not fp.exists():
        return
    data = _load(fp)
    report = FinalReport(**data)
    # 基本信息
    assert report.total_chars > 0
    assert report.total_chunks > 0
    # 维度评分
    assert len(report.dimension_scores) == 8, f"应有8个维度，实际{len(report.dimension_scores)}"
    # 不应全部相同
    scores = [ds.score for ds in report.dimension_scores]
    assert len(set(scores)) > 1, f"所有评分相同: {scores}"
    # evidence非空率
    with_evidence = sum(1 for ds in report.dimension_scores if ds.evidence)
    assert with_evidence >= 4, f"只有{with_evidence}/8个维度有证据"
    # 缺陷
    for d in report.defects:
        assert d.rule_id.startswith("D"), f"缺陷ID格式错误: {d.rule_id}"


def test_report_markdown_exists():
    """report.md存在且非空"""
    fp = OUTPUT / "report.md"
    if not fp.exists():
        return
    content = fp.read_text(encoding="utf-8")
    assert len(content) > 500
    assert "# 小说评价报告" in content
    assert "## 维度评分" in content
    assert "## 节奏曲线" in content
