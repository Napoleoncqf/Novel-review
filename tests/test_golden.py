"""T13: Golden case回归测试 — 验证schema稳定性、字段完整性和跨阶段一致性"""
import sys
import json
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from novel_review.models import (
    ChunkManifest, LightResult, DeepResult,
    CrossChunkAnalysis, FinalReport,
)

GOLDEN_DIR = Path(__file__).parent / "golden"
CASES = [d.name for d in sorted(GOLDEN_DIR.iterdir()) if d.is_dir()]

DIMENSION_IDS = {
    "plot", "character", "writing", "worldbuilding",
    "theme", "dialogue", "emotion", "innovation",
}


def _load(path: Path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


# ---------- 参数化：每个 case 目录跑一遍 ----------

@pytest.fixture(params=CASES)
def case_dir(request):
    return GOLDEN_DIR / request.param


# ---- Manifest ----

class TestManifest:
    def test_schema(self, case_dir):
        data = _load(case_dir / "manifest.json")
        m = ChunkManifest(**data)
        assert m.total_chunks == len(m.chunks)
        assert m.total_chars > 0

    def test_chunk_ids_sequential(self, case_dir):
        data = _load(case_dir / "manifest.json")
        m = ChunkManifest(**data)
        ids = [c.chunk_id for c in m.chunks]
        assert ids == list(range(len(ids)))

    def test_char_ranges_contiguous(self, case_dir):
        data = _load(case_dir / "manifest.json")
        m = ChunkManifest(**data)
        for i in range(1, len(m.chunks)):
            assert m.chunks[i].char_range[0] == m.chunks[i - 1].char_range[1]


# ---- Light results ----

class TestLight:
    def _lights(self, case_dir):
        return sorted(case_dir.glob("light_*.json"))

    def test_schema(self, case_dir):
        for fp in self._lights(case_dir):
            lr = LightResult(**_load(fp))
            assert 1 <= lr.pacing_score <= 5

    def test_count_matches_manifest(self, case_dir):
        manifest = ChunkManifest(**_load(case_dir / "manifest.json"))
        assert len(self._lights(case_dir)) == manifest.total_chunks


# ---- Deep results ----

class TestDeep:
    def _deeps(self, case_dir):
        return sorted(case_dir.glob("deep_*.json"))

    def test_schema(self, case_dir):
        for fp in self._deeps(case_dir):
            dr = DeepResult(**_load(fp))
            assert 1 <= dr.pacing_score <= 5
            assert 1 <= dr.information_density <= 5

    def test_deep_subset_of_manifest(self, case_dir):
        """精读块必须是manifest中标记为deep的子集"""
        manifest = ChunkManifest(**_load(case_dir / "manifest.json"))
        deep_ids_manifest = {
            c.chunk_id for c in manifest.chunks if c.analysis_depth == "deep"
        }
        deep_ids_actual = {
            DeepResult(**_load(fp)).chunk_id for fp in self._deeps(case_dir)
        }
        assert deep_ids_actual == deep_ids_manifest

    def test_evidence_quotes_not_too_long(self, case_dir):
        for fp in self._deeps(case_dir):
            dr = DeepResult(**_load(fp))
            for ev in dr.evidence:
                assert len(ev.quote) <= 60, f"chunk {dr.chunk_id}: quote过长({len(ev.quote)}字)"

    def test_defect_ids_format(self, case_dir):
        for fp in self._deeps(case_dir):
            dr = DeepResult(**_load(fp))
            for d in dr.defects_detected:
                assert d.startswith("D"), f"缺陷ID格式错误: {d}"


# ---- CrossChunkAnalysis ----

class TestCrossChunk:
    def test_schema(self, case_dir):
        data = _load(case_dir / "cross_chunk.json")
        cca = CrossChunkAnalysis(**data)
        manifest = ChunkManifest(**_load(case_dir / "manifest.json"))
        assert len(cca.pacing_curve) == manifest.total_chunks
        assert len(cca.emotion_curve) == manifest.total_chunks

    def test_coverage_ratio(self, case_dir):
        data = _load(case_dir / "cross_chunk.json")
        cca = CrossChunkAnalysis(**data)
        ratio = cca.coverage["ratio"]
        assert 0.0 <= ratio <= 1.0

    def test_foreshadowing_planted_before_resolved(self, case_dir):
        data = _load(case_dir / "cross_chunk.json")
        cca = CrossChunkAnalysis(**data)
        for fp in cca.foreshadowing_pairs:
            if fp.resolved_chunk is not None:
                assert fp.planted_chunk <= fp.resolved_chunk, (
                    f"伏笔时序错误: planted={fp.planted_chunk} > resolved={fp.resolved_chunk}"
                )


# ---- Evidence index ----

class TestEvidenceIndex:
    def test_structure(self, case_dir):
        data = _load(case_dir / "evidence_index.json")
        assert isinstance(data, list)
        for item in data:
            assert "quote" in item
            assert "chunk_id" in item

    def test_chunk_ids_valid(self, case_dir):
        manifest = ChunkManifest(**_load(case_dir / "manifest.json"))
        valid_ids = {c.chunk_id for c in manifest.chunks}
        evidence = _load(case_dir / "evidence_index.json")
        for item in evidence:
            assert item["chunk_id"] in valid_ids, f"证据引用了不存在的chunk: {item['chunk_id']}"


# ---- Final report ----

class TestFinalReport:
    def _report(self, case_dir):
        return FinalReport(**_load(case_dir / "report.json"))

    def test_schema(self, case_dir):
        r = self._report(case_dir)
        assert r.total_chars > 0
        assert r.total_chunks > 0

    def test_8_dimensions(self, case_dir):
        r = self._report(case_dir)
        assert len(r.dimension_scores) == 8
        ids = {ds.dimension_id for ds in r.dimension_scores}
        assert ids == DIMENSION_IDS

    def test_scores_in_range(self, case_dir):
        r = self._report(case_dir)
        for ds in r.dimension_scores:
            assert 1.0 <= ds.score <= 10.0, f"{ds.dimension_id}: {ds.score} 超出范围"

    def test_weighted_total_in_range(self, case_dir):
        r = self._report(case_dir)
        assert 1.0 <= r.weighted_total <= 10.0

    def test_stars_in_range(self, case_dir):
        r = self._report(case_dir)
        assert 1 <= r.recommendation_stars <= 5

    def test_defect_ids_valid(self, case_dir):
        r = self._report(case_dir)
        for d in r.defects:
            assert d.rule_id.startswith("D")

    def test_two_perspectives(self, case_dir):
        r = self._report(case_dir)
        perspectives = {p.perspective for p in r.perspectives}
        assert perspectives == {"literary", "commercial"}

    def test_pacing_matches_manifest(self, case_dir):
        r = self._report(case_dir)
        manifest = ChunkManifest(**_load(case_dir / "manifest.json"))
        assert len(r.pacing_curve) == manifest.total_chunks

    def test_sampled_mode_has_low_confidence(self, case_dir):
        """抽样模式下，至少有一个维度confidence != high"""
        r = self._report(case_dir)
        if r.read_mode == "sampled":
            confidences = [ds.confidence for ds in r.dimension_scores]
            assert "low" in confidences or "medium" in confidences, (
                "抽样模式下应有non-high confidence维度"
            )
