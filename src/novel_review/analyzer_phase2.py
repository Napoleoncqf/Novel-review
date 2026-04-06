"""T09: Phase2跨块综合分析"""
from __future__ import annotations

from .models import (
    LightResult, DeepResult, CrossChunkAnalysis,
    CharacterArc, ForeshadowingPair,
)
from .storage import Storage


def _extract_keywords(text: str) -> set[str]:
    """提取2字以上的中文关键词片段（滑动窗口2-4字）"""
    import re
    # 去掉标点，只保留中文和字母数字
    clean = re.sub(r'[^\u4e00-\u9fff\w]', '', text)
    keywords = set()
    for n in (2, 3, 4):
        for i in range(len(clean) - n + 1):
            keywords.add(clean[i:i+n])
    return keywords


def _fuzzy_find(desc: str, planted: dict[str, int]) -> str | None:
    """在planted中查找与desc最匹配的key，用关键词重叠度判断"""
    if desc in planted:
        return desc
    desc_kw = _extract_keywords(desc)
    if not desc_kw:
        return None
    best_key, best_ratio = None, 0.0
    for key in planted:
        key_kw = _extract_keywords(key)
        if not key_kw:
            continue
        overlap = len(desc_kw & key_kw)
        smaller = min(len(desc_kw), len(key_kw))
        ratio = overlap / smaller if smaller > 0 else 0
        if ratio > best_ratio:
            best_ratio = ratio
            best_key = key
    return best_key if best_ratio >= 0.25 else None


def run_phase2(
    light_results: list[LightResult],
    deep_results: list[DeepResult],
    storage: Storage,
) -> CrossChunkAnalysis:
    # 节奏曲线（来自light，全量覆盖）
    pacing = [lr.pacing_score for lr in sorted(light_results, key=lambda x: x.chunk_id)]

    # 情绪曲线（来自deep）
    deep_map = {dr.chunk_id: dr for dr in deep_results}
    emotion = []
    for lr in sorted(light_results, key=lambda x: x.chunk_id):
        if lr.chunk_id in deep_map:
            emotion.append(deep_map[lr.chunk_id].emotional_tone or "未知")
        else:
            emotion.append("未精读")

    # 人物弧光
    char_data: dict[str, CharacterArc] = {}
    for lr in light_results:
        for name in lr.characters_present:
            clean = name.split("（")[0].split("(")[0].strip()
            if not clean:
                continue
            if clean not in char_data:
                char_data[clean] = CharacterArc(name=clean)
            char_data[clean].appearances.append(lr.chunk_id)
    # 从deep结果补充traits
    for dr in deep_results:
        for name in dr.characters_present:
            clean = name.split("（")[0].split("(")[0].strip()
            if clean in char_data and name != clean:
                detail = name.replace(clean, "").strip("（）() ")
                if detail and detail not in char_data[clean].traits:
                    char_data[clean].traits.append(detail)
    # 只保留出场>=3次的角色
    arcs = [a for a in char_data.values() if len(a.appearances) >= 3]
    arcs.sort(key=lambda a: len(a.appearances), reverse=True)

    # 伏笔配对（模糊匹配：描述文本有足够重叠即视为同一伏笔）
    foreshadowing_pairs: list[ForeshadowingPair] = []
    planted: dict[str, int] = {}  # description -> planted_chunk_id
    for dr in sorted(deep_results, key=lambda x: x.chunk_id):
        for f in dr.foreshadowing:
            if f.status == "planted":
                planted[f.description] = dr.chunk_id
            elif f.status == "resolved":
                match_key = _fuzzy_find(f.description, planted)
                p_chunk = planted.pop(match_key, None) if match_key else None
                foreshadowing_pairs.append(ForeshadowingPair(
                    description=f.description,
                    planted_chunk=p_chunk or 0,
                    resolved_chunk=dr.chunk_id,
                    status="resolved",
                ))
    # 未回收的伏笔
    for desc, p_chunk in planted.items():
        foreshadowing_pairs.append(ForeshadowingPair(
            description=desc,
            planted_chunk=p_chunk,
            status="open",
        ))

    # 设定冲突（简单收集）
    setting_conflicts: list[str] = []
    seen_settings: dict[str, str] = {}
    for dr in sorted(deep_results, key=lambda x: x.chunk_id):
        for elem in dr.worldbuilding_elements:
            key = elem.split("：")[0] if "：" in elem else elem[:10]
            if key in seen_settings and seen_settings[key] != elem:
                setting_conflicts.append(f"块{dr.chunk_id}: {key}前后不一致")
            seen_settings[key] = elem

    # coverage
    total = len(light_results)
    deep_count = len(deep_results)
    coverage = {
        "total_chunks": total,
        "deep_chunks": deep_count,
        "ratio": round(deep_count / total, 2) if total > 0 else 0,
    }

    analysis = CrossChunkAnalysis(
        pacing_curve=pacing,
        character_arcs=arcs[:10],  # 最多10个角色
        foreshadowing_pairs=foreshadowing_pairs,
        setting_conflicts=setting_conflicts,
        emotion_curve=emotion,
        coverage=coverage,
    )

    # 落盘
    storage.save_json("phase2/cross_chunk_analysis.json", analysis.model_dump())

    # 证据索引
    evidence_index = []
    for dr in deep_results:
        for ev in dr.evidence:
            evidence_index.append({
                "chunk_id": dr.chunk_id,
                "chapter_ref": dr.chapter_ref,
                **ev.model_dump(),
            })
    storage.save_json("phase2/evidence_index.json", evidence_index)

    return analysis
