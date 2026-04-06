"""LLM输出规范化 — 处理LLM返回格式不一致的问题"""
from __future__ import annotations


def normalize_string_list(items: list) -> list[str]:
    """将可能包含dict的列表转换为string列表"""
    result = []
    for item in items:
        if isinstance(item, str):
            result.append(item)
        elif isinstance(item, dict):
            # 尝试拼接dict的值
            parts = []
            name = item.get("name", item.get("entity", ""))
            if name:
                parts.append(str(name))
            for key in ["behavior", "action", "state", "emotion", "status",
                        "change", "description", "detail", "quote", "content"]:
                val = item.get(key)
                if val:
                    parts.append(str(val))
            result.append("（".join(parts[:2]) + "）" if len(parts) > 1 else parts[0] if parts else str(item))
        else:
            result.append(str(item))
    return result


def normalize_evidence_list(items: list) -> list[dict]:
    """规范化证据列表"""
    result = []
    for item in items:
        if isinstance(item, dict):
            ev = {
                "quote": str(item.get("quote", ""))[:60],
                "char_range": item.get("char_range", [0, 0]),
                "chapter_ref": str(item.get("chapter_ref", "")),
                "reason": str(item.get("reason", "")),
            }
            # char_range可能是各种格式
            cr = ev["char_range"]
            if isinstance(cr, list) and len(cr) == 2:
                ev["char_range"] = (int(cr[0]), int(cr[1]))
            elif isinstance(cr, str):
                ev["char_range"] = (0, 0)
            else:
                ev["char_range"] = (0, 0)
            result.append(ev)
    return result


def normalize_foreshadowing(items: list) -> list[dict]:
    """规范化伏笔列表"""
    result = []
    for item in items:
        if isinstance(item, dict):
            result.append({
                "description": str(item.get("description", "")),
                "status": str(item.get("status", "planted")),
                "chunk_id": int(item.get("chunk_id", 0)),
            })
        elif isinstance(item, str):
            result.append({"description": item, "status": "planted", "chunk_id": 0})
    return result


def normalize_state_changes(items: list) -> list[dict]:
    """规范化状态变化列表"""
    result = []
    for item in items:
        if isinstance(item, dict):
            result.append({
                "entity": str(item.get("entity", item.get("name", ""))),
                "change": str(item.get("change", item.get("description", ""))),
            })
        elif isinstance(item, str):
            result.append({"entity": "", "change": item})
    return result


def normalize_deep_data(data: dict) -> dict:
    """规范化深度分析的LLM返回数据"""
    # emotional_tone: LLM有时返回list而非string
    if "emotional_tone" in data and isinstance(data["emotional_tone"], list):
        data["emotional_tone"] = "、".join(str(x) for x in data["emotional_tone"])
    if "emotional_tone" in data and not isinstance(data["emotional_tone"], str):
        data["emotional_tone"] = str(data["emotional_tone"])
    if "characters_present" in data:
        data["characters_present"] = normalize_string_list(data["characters_present"])
    if "notable_writing" in data:
        data["notable_writing"] = normalize_string_list(data["notable_writing"])
    if "worldbuilding_elements" in data:
        data["worldbuilding_elements"] = normalize_string_list(data["worldbuilding_elements"])
    if "plot_events" in data:
        data["plot_events"] = normalize_string_list(data["plot_events"])
    if "evidence" in data:
        data["evidence"] = normalize_evidence_list(data["evidence"])
    if "foreshadowing" in data:
        data["foreshadowing"] = normalize_foreshadowing(data["foreshadowing"])
    if "defects_detected" in data:
        # 可能是字符串列表或dict列表，统一归一化为"D0X"格式
        import re
        defs = []
        for d in data["defects_detected"]:
            raw = ""
            if isinstance(d, str):
                raw = d
            elif isinstance(d, dict):
                raw = str(d.get("id", d.get("rule_id", "")))
            # 提取D0X格式的ID
            m = re.match(r"(D\d{2})", raw)
            if m:
                defs.append(m.group(1))
            elif raw:
                defs.append(raw)
        data["defects_detected"] = defs
    return data


def normalize_light_data(data: dict) -> dict:
    """规范化轻筛分析的LLM返回数据"""
    if "characters_present" in data:
        data["characters_present"] = normalize_string_list(data["characters_present"])
    if "plot_events" in data:
        data["plot_events"] = normalize_string_list(data["plot_events"])
    if "candidate_flags" in data:
        data["candidate_flags"] = normalize_string_list(data["candidate_flags"])
    if "state_changes" in data:
        data["state_changes"] = normalize_state_changes(data["state_changes"])
    # pacing_score可能是浮点数
    if "pacing_score" in data:
        try:
            data["pacing_score"] = max(1, min(5, int(float(data["pacing_score"]))))
        except (ValueError, TypeError):
            data["pacing_score"] = 3
    return data
