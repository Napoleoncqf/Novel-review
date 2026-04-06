"""T11: Phase3最终评价生成 — 双视角评分"""
from __future__ import annotations
import json

from .models import (
    CrossChunkAnalysis, DeepResult, LightResult,
    FinalReport, DimensionScore, PerspectiveReview, DefectReport, Evidence,
)
from .llm_client import LLMClient
from .config import build_rubric_text, get_all_dimensions

SYSTEM_LITERARY = """\
你是一位严格的文学评论者，关注语言艺术、叙事技巧、主题深度和人物心理刻画。
你不关心商业表现，只评价文学价值。评价时必须引用已提供的证据，不允许编造新引用。
只输出合法JSON。"""

SYSTEM_COMMERCIAL = """\
你是一位网络小说编辑，关注可读性、节奏感、爽点设置、读者粘性。
你从商业角度评估作品的市场表现潜力。评价时必须引用已提供的证据。
只输出合法JSON。"""

EVAL_TEMPLATE = """\
请基于以下小说分析数据，从{perspective}生成评价。

小说概况：共{total_chars}字，{total_chunks}块，精读{deep_count}块（覆盖率{coverage_pct}%）。

关键情节摘要：
{plot_summary}

人物弧光：
{character_summary}

证据索引（可引用）：
{evidence_text}

缺陷检测结果：
{defect_text}

评分标准（rubric）：
{rubric}

请输出JSON，包含：
- dimension_scores: 数组，每项含dimension_id、dimension_name、score(1-10浮点数)、confidence(high/medium/low)、reason(<=100字)、evidence(引用已有证据的quote和reason)
- strengths: 优点3条（string数组）
- weaknesses: 不足3条（string数组）
- verdict: 核心判断1句话
- genre_guess: 类型推断
- one_line_summary: 一句话总评(<=50字)
- improvement_suggestions: 改进建议2-3条"""


async def run_phase3(
    analysis: CrossChunkAnalysis,
    light_results: list[LightResult],
    deep_results: list[DeepResult],
    llm: LLMClient,
    total_chars: int,
    title: str = "",
) -> FinalReport:
    rubric = build_rubric_text()
    all_dims = get_all_dimensions()

    # 构建摘要
    plot_lines = []
    for lr in sorted(light_results, key=lambda x: x.chunk_id):
        if lr.plot_events:
            plot_lines.append(f"[{lr.chapter_ref}] {'；'.join(lr.plot_events[:2])}")
    plot_summary = "\n".join(plot_lines[:40])

    char_lines = []
    for arc in analysis.character_arcs[:8]:
        traits = "、".join(arc.traits[:3]) if arc.traits else "特征待定"
        char_lines.append(f"- {arc.name}：出场{len(arc.appearances)}次，{traits}")
    character_summary = "\n".join(char_lines)

    # 证据
    evidence_items = []
    for dr in deep_results:
        for ev in dr.evidence:
            evidence_items.append(f"[{dr.chapter_ref}] \"{ev.quote}\" — {ev.reason}")
    evidence_text = "\n".join(evidence_items[:50])

    # 缺陷
    defect_lines = []
    for dr in deep_results:
        for d_id in dr.defects_detected:
            defect_lines.append(f"块{dr.chunk_id}({dr.chapter_ref}): {d_id}")
    defect_text = "\n".join(defect_lines) if defect_lines else "未检测到明显缺陷"

    coverage = analysis.coverage
    coverage_pct = round(coverage.get("ratio", 0) * 100)

    common_kwargs = dict(
        total_chars=total_chars,
        total_chunks=coverage.get("total_chunks", 0),
        deep_count=coverage.get("deep_chunks", 0),
        coverage_pct=coverage_pct,
        plot_summary=plot_summary[:4000],
        character_summary=character_summary[:1500],
        evidence_text=evidence_text[:3000],
        defect_text=defect_text[:1000],
        rubric=rubric[:3000],
    )

    # 双视角并行调用
    literary_msg = EVAL_TEMPLATE.format(perspective="文学性视角", **common_kwargs)
    commercial_msg = EVAL_TEMPLATE.format(perspective="商业性视角", **common_kwargs)

    lit_data = await llm.ask_json(SYSTEM_LITERARY, literary_msg)
    com_data = await llm.ask_json(SYSTEM_COMMERCIAL, commercial_msg)

    # 构建id查找表（支持中文名/英文id/模糊匹配）
    dim_id_lookup: dict[str, str] = {}
    for d in all_dims:
        dim_id_lookup[d["id"]] = d["id"]
        dim_id_lookup[d["name"]] = d["id"]
        # 常见变体
        dim_id_lookup[d["id"].lower()] = d["id"]
    # 额外映射
    _extra = {
        "情节": "plot", "情节结构": "plot", "plot_structure": "plot",
        "人物": "character", "人物塑造": "character", "角色": "character",
        "文笔": "writing", "文笔质量": "writing", "语言": "writing",
        "世界观": "worldbuilding", "世界观构建": "worldbuilding", "设定": "worldbuilding",
        "主题": "theme", "主题深度": "theme",
        "对话": "dialogue", "对话质量": "dialogue",
        "情感": "emotion", "情感感染力": "emotion", "感染力": "emotion",
        "创新": "innovation", "创新性": "innovation", "新颖性": "innovation",
    }
    dim_id_lookup.update(_extra)

    def _resolve_dim_id(raw: str) -> str:
        if raw in dim_id_lookup:
            return dim_id_lookup[raw]
        raw_lower = raw.lower().strip()
        if raw_lower in dim_id_lookup:
            return dim_id_lookup[raw_lower]
        # 子串匹配
        for key, val in dim_id_lookup.items():
            if key in raw or raw in key:
                return val
        return ""

    # 合并评分（取两视角均值）
    dim_scores_map: dict[str, list[float]] = {}
    all_evidence: dict[str, list] = {}
    all_reasons: dict[str, list[str]] = {}

    for src in [lit_data, com_data]:
        for ds in src.get("dimension_scores", []):
            raw_id = ds.get("dimension_id", "") or ds.get("dimension_name", "")
            did = _resolve_dim_id(str(raw_id))
            if did:
                dim_scores_map.setdefault(did, []).append(float(ds.get("score", 5)))
                all_evidence.setdefault(did, []).extend(ds.get("evidence", []))
                all_reasons.setdefault(did, []).append(ds.get("reason", ""))

    # 构建维度→证据的fallback映射（从deep_results中提取）
    _dim_keywords = {
        "plot": ["情节", "伏笔", "高潮", "转折", "冲突", "节奏"],
        "character": ["人物", "角色", "性格", "成长", "动机", "心理"],
        "writing": ["文笔", "语言", "修辞", "描写", "叙述", "用词"],
        "worldbuilding": ["设定", "世界", "背景", "时代", "环境"],
        "theme": ["主题", "思想", "价值", "意义", "隐喻"],
        "dialogue": ["对话", "台词", "口吻", "语气"],
        "emotion": ["情感", "感动", "泪目", "震撼", "压抑", "温馨"],
        "innovation": ["创新", "新颖", "独特", "套路"],
    }
    _fallback_evidence: dict[str, list[Evidence]] = {did: [] for did in _dim_keywords}
    for dr in deep_results:
        for ev in dr.evidence:
            for did, kws in _dim_keywords.items():
                if any(kw in ev.reason or kw in ev.quote for kw in kws):
                    if len(_fallback_evidence[did]) < 3:
                        _fallback_evidence[did].append(ev)

    dimension_scores = []
    for d in all_dims:
        did = d["id"]
        scores = dim_scores_map.get(did, [5.0])
        avg = round(sum(scores) / len(scores), 1)
        conf = "high" if coverage_pct >= 80 else ("medium" if coverage_pct >= 50 else "low")
        if did in ("writing", "theme", "emotion") and coverage_pct < 60:
            conf = "low"
        reasons = all_reasons.get(did, [""])
        evs = []
        # 先尝试LLM返回的evidence
        for e in all_evidence.get(did, [])[:3]:
            if isinstance(e, dict):
                try:
                    cr = e.get("char_range", [0, 0])
                    if isinstance(cr, list) and len(cr) == 2:
                        cr = (int(cr[0]), int(cr[1]))
                    else:
                        cr = (0, 0)
                    evs.append(Evidence(
                        quote=str(e.get("quote", ""))[:60],
                        char_range=cr,
                        chapter_ref=str(e.get("chapter_ref", "")),
                        reason=str(e.get("reason", "")),
                    ))
                except Exception:
                    pass
        # fallback: 如果LLM没返回evidence，从deep_results按关键词匹配
        if not evs and did in _fallback_evidence:
            evs = _fallback_evidence[did][:2]
        dimension_scores.append(DimensionScore(
            dimension_id=did,
            dimension_name=d["name"],
            score=avg,
            confidence=conf,
            reason="｜".join(r for r in reasons if r)[:200],
            evidence=evs,
        ))

    # 加权总分
    weighted = 0.0
    for ds in dimension_scores:
        w = next((d["weight"] for d in all_dims if d["id"] == ds.dimension_id), 0)
        weighted += ds.score * w
    weighted = round(weighted, 1)

    # 推荐星级
    if weighted >= 8:
        stars = 5
    elif weighted >= 7:
        stars = 4
    elif weighted >= 5.5:
        stars = 3
    elif weighted >= 4:
        stars = 2
    else:
        stars = 1

    # 缺陷报告（使用独立检测引擎）
    from .defect_rules import run_defect_detection
    defects = run_defect_detection(light_results, deep_results, analysis)

    # 视角
    perspectives = [
        PerspectiveReview(
            perspective="literary",
            strengths=lit_data.get("strengths", []),
            weaknesses=lit_data.get("weaknesses", []),
            verdict=lit_data.get("verdict", ""),
        ),
        PerspectiveReview(
            perspective="commercial",
            strengths=com_data.get("strengths", []),
            weaknesses=com_data.get("weaknesses", []),
            verdict=com_data.get("verdict", ""),
        ),
    ]

    return FinalReport(
        title=title,
        total_chars=total_chars,
        total_chunks=coverage.get("total_chunks", 0),
        genre_guess=lit_data.get("genre_guess", com_data.get("genre_guess", "")),
        read_mode="full" if coverage_pct >= 80 else "sampled",
        deep_ratio=coverage.get("ratio", 0),
        confidence_note=_build_confidence_note(coverage, coverage_pct),
        dimension_scores=dimension_scores,
        weighted_total=weighted,
        recommendation_stars=stars,
        one_line_summary=lit_data.get("one_line_summary", com_data.get("one_line_summary", "")),
        perspectives=perspectives,
        defects=defects,
        pacing_curve=analysis.pacing_curve,
        character_arcs=analysis.character_arcs,
        improvement_suggestions=lit_data.get("improvement_suggestions", [])
                                + com_data.get("improvement_suggestions", []),
    )


def _build_confidence_note(coverage: dict, coverage_pct: int) -> str:
    total = coverage.get("total_chunks", 0)
    deep = coverage.get("deep_chunks", 0)
    if coverage_pct >= 100:
        return "全量精读"
    if coverage_pct >= 80:
        return f"精读{deep}/{total}块（{coverage_pct}%），覆盖度高，结论可信"
    parts = [f"抽样精读{deep}/{total}块（{coverage_pct}%）"]
    if coverage_pct < 50:
        parts.append("文笔、主题、情感维度置信度较低")
    parts.append("情节结构和人物弧光基于全量轻筛，可信度较高")
    return "；".join(parts)
