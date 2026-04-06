"""T10: 缺陷检测引擎 — 基于Phase1/Phase2产物的启发式规则"""
from __future__ import annotations
from dataclasses import dataclass, field

from .models import LightResult, DeepResult, CrossChunkAnalysis, DefectReport, Evidence


@dataclass
class DefectFinding:
    rule_id: str
    rule_name: str
    chunks: list[int] = field(default_factory=list)
    description: str = ""
    evidence: list[Evidence] = field(default_factory=list)

    @property
    def severity(self) -> str:
        n = len(self.chunks)
        if n >= 5:
            return "severe"
        if n >= 2:
            return "medium"
        return "mild"

    def to_report(self) -> DefectReport:
        return DefectReport(
            rule_id=self.rule_id,
            rule_name=self.rule_name,
            location=f"块{'、'.join(str(c) for c in self.chunks)}",
            severity=self.severity,
            description=self.description,
            evidence=self.evidence[:3],
        )


def run_defect_detection(
    light_results: list[LightResult],
    deep_results: list[DeepResult],
    analysis: CrossChunkAnalysis,
) -> list[DefectReport]:
    """运行所有D01-D08规则，返回检测结果"""
    findings: list[DefectFinding] = []

    lights = sorted(light_results, key=lambda x: x.chunk_id)
    deeps = sorted(deep_results, key=lambda x: x.chunk_id)
    deep_map = {dr.chunk_id: dr for dr in deeps}

    # 收集LLM已标注的缺陷（Phase1 deep中的defects_detected）
    llm_defects: dict[str, list[int]] = {}
    for dr in deeps:
        for d_id in dr.defects_detected:
            llm_defects.setdefault(d_id, []).append(dr.chunk_id)

    # ── D04: 节奏塌陷 ──
    d04 = _detect_d04_pacing_collapse(lights)
    if d04:
        findings.append(d04)

    # ── D07: 注水严重 ──
    d07 = _detect_d07_padding(deeps)
    if d07:
        findings.append(d07)

    # ── D08: 伏笔断裂 ──
    d08 = _detect_d08_broken_foreshadowing(analysis)
    if d08:
        findings.append(d08)

    # ── D06: 设定遗忘 ──
    d06 = _detect_d06_setting_forgotten(analysis)
    if d06:
        findings.append(d06)

    # ── D03, D05: 来自LLM标注（无法纯启发式检测，依赖Phase1 deep判断）──
    for rule_id, rule_name in [("D01", "龙傲天"), ("D02", "金手指过度"),
                                ("D03", "感情线突兀"), ("D05", "人设崩塌")]:
        if rule_id in llm_defects:
            findings.append(DefectFinding(
                rule_id=rule_id,
                rule_name=rule_name,
                chunks=llm_defects[rule_id],
                description=f"LLM在{len(llm_defects[rule_id])}个块中标注了{rule_name}",
            ))

    # 去重：如果启发式和LLM都检测到同一规则，合并块列表
    merged = _merge_findings(findings)

    return [f.to_report() for f in merged]


def _detect_d04_pacing_collapse(lights: list[LightResult]) -> DefectFinding | None:
    """D04: 连续3块plot_progression=no且pacing_score<=2"""
    consecutive = []
    collapse_chunks = []

    for lr in lights:
        is_no = lr.plot_progression.lower().startswith("no")
        is_slow = lr.pacing_score <= 2
        if is_no and is_slow:
            consecutive.append(lr.chunk_id)
        else:
            if len(consecutive) >= 3:
                collapse_chunks.extend(consecutive)
            consecutive = []

    if len(consecutive) >= 3:
        collapse_chunks.extend(consecutive)

    if collapse_chunks:
        return DefectFinding(
            rule_id="D04",
            rule_name="节奏塌陷",
            chunks=collapse_chunks,
            description=f"连续{len(collapse_chunks)}块无主线推进且节奏松散",
        )
    return None


def _detect_d07_padding(deeps: list[DeepResult]) -> DefectFinding | None:
    """D07: 连续2块information_density<=2"""
    consecutive = []
    padding_chunks = []

    for dr in deeps:
        if dr.information_density <= 2:
            consecutive.append(dr.chunk_id)
        else:
            if len(consecutive) >= 2:
                padding_chunks.extend(consecutive)
            consecutive = []

    if len(consecutive) >= 2:
        padding_chunks.extend(consecutive)

    if padding_chunks:
        return DefectFinding(
            rule_id="D07",
            rule_name="注水严重",
            chunks=padding_chunks,
            description=f"{len(padding_chunks)}块信息密度过低（<=2）",
        )
    return None


def _detect_d08_broken_foreshadowing(analysis: CrossChunkAnalysis) -> DefectFinding | None:
    """D08: 伏笔埋设后>=5块仍未回收"""
    broken_chunks = set()
    broken_count = 0
    total_chunks = len(analysis.pacing_curve) if analysis.pacing_curve else 0

    for fp in analysis.foreshadowing_pairs:
        if fp.status in ("open", "planted", "unresolved"):
            gap = total_chunks - fp.planted_chunk
            if gap >= 5:
                broken_chunks.add(fp.planted_chunk)
                broken_count += 1

    if broken_chunks:
        return DefectFinding(
            rule_id="D08",
            rule_name="伏笔断裂",
            chunks=sorted(broken_chunks),
            description=f"{broken_count}条伏笔未回收",
        )
    return None


def _detect_d06_setting_forgotten(analysis: CrossChunkAnalysis) -> DefectFinding | None:
    """D06: 设定前后不一致"""
    if analysis.setting_conflicts:
        # 从冲突描述中提取块号
        chunks = []
        for conflict in analysis.setting_conflicts:
            import re
            m = re.search(r"块(\d+)", conflict)
            if m:
                chunks.append(int(m.group(1)))
        return DefectFinding(
            rule_id="D06",
            rule_name="设定遗忘",
            chunks=chunks or [0],
            description=f"{len(analysis.setting_conflicts)}处设定前后不一致",
        )
    return None


def _merge_findings(findings: list[DefectFinding]) -> list[DefectFinding]:
    """合并同一rule_id的findings"""
    merged: dict[str, DefectFinding] = {}
    for f in findings:
        if f.rule_id in merged:
            existing = merged[f.rule_id]
            # 合并块列表并去重
            all_chunks = sorted(set(existing.chunks + f.chunks))
            existing.chunks = all_chunks
            if f.description and not existing.description:
                existing.description = f.description
            existing.evidence.extend(f.evidence)
        else:
            merged[f.rule_id] = f
    return sorted(merged.values(), key=lambda x: x.rule_id)
