"""T12: 报告输出模块 — Markdown + JSON"""
from __future__ import annotations
from .models import FinalReport
from .storage import Storage


def render_pacing_chart(curve: list[int], width: int = 60) -> str:
    if not curve:
        return "（无节奏数据）"
    lines = []
    max_val = max(curve) if curve else 5
    bar_chars = "▁▂▃▄▅▆▇█"
    for i, val in enumerate(curve):
        idx = int((val - 1) / (max_val - 1) * (len(bar_chars) - 1)) if max_val > 1 else 4
        bar = bar_chars[idx]
        lines.append(bar)
    # 每行最多60个
    rows = []
    for start in range(0, len(lines), width):
        rows.append("".join(lines[start:start + width]))
    chart = "\n".join(rows)
    return f"块序号 →\n{chart}\n(▁=1 ▃=2 ▅=3 ▆=4 █=5)"


def render_markdown(report: FinalReport) -> str:
    lines = []

    # 标题
    lines.append(f"# 小说评价报告：{report.title or '未知'}")
    lines.append("")

    # 基本信息
    lines.append("## 基本信息")
    lines.append(f"- 字数：{report.total_chars:,}")
    lines.append(f"- 分块数：{report.total_chunks}")
    lines.append(f"- 类型推断：{report.genre_guess}")
    lines.append("")

    # 覆盖度
    lines.append("## 分析覆盖度")
    lines.append(f"- 阅读模式：{report.read_mode}")
    lines.append(f"- 精读占比：{report.deep_ratio:.0%}")
    lines.append(f"- {report.confidence_note}")
    lines.append("")

    # 总评
    lines.append("## 总评")
    lines.append(f"**{report.one_line_summary}**")
    lines.append("")
    lines.append(f"- 加权总分：**{report.weighted_total}/10**")
    lines.append(f"- 推荐指数：{'★' * report.recommendation_stars}{'☆' * (5 - report.recommendation_stars)}")
    lines.append("")

    # 维度评分
    lines.append("## 维度评分")
    lines.append("")
    lines.append("| 维度 | 分数 | 置信度 | 理由 |")
    lines.append("|------|------|--------|------|")
    for ds in report.dimension_scores:
        reason = ds.reason[:80].replace("|", "｜")
        lines.append(f"| {ds.dimension_name} | {ds.score} | {ds.confidence} | {reason} |")
    lines.append("")

    # 证据引用
    lines.append("### 关键证据")
    for ds in report.dimension_scores:
        if ds.evidence:
            lines.append(f"\n**{ds.dimension_name}**")
            for ev in ds.evidence[:2]:
                lines.append(f"  - \"{ev.quote}\" — {ev.reason}")
    lines.append("")

    # 双视角
    lines.append("## 双视角点评")
    for p in report.perspectives:
        pname = "文学性视角" if p.perspective == "literary" else "商业性视角"
        lines.append(f"\n### {pname}")
        lines.append("**优点：**")
        for s in p.strengths:
            lines.append(f"- {s}")
        lines.append("**不足：**")
        for w in p.weaknesses:
            lines.append(f"- {w}")
        lines.append(f"\n**核心判断：** {p.verdict}")
    lines.append("")

    # 缺陷
    if report.defects:
        lines.append("## 缺陷检测报告")
        lines.append("")
        lines.append("| 规则 | 名称 | 位置 | 严重程度 |")
        lines.append("|------|------|------|----------|")
        for d in report.defects:
            lines.append(f"| {d.rule_id} | {d.rule_name} | {d.location} | {d.severity} |")
        lines.append("")
    else:
        lines.append("## 缺陷检测报告\n\n未检测到明显缺陷。\n")

    # 节奏曲线
    lines.append("## 节奏曲线")
    lines.append("```")
    lines.append(render_pacing_chart(report.pacing_curve))
    lines.append("```")
    lines.append("")

    # 人物图谱
    lines.append("## 人物图谱")
    for arc in report.character_arcs[:8]:
        span = f"块{min(arc.appearances)}-{max(arc.appearances)}" if arc.appearances else "未知"
        traits = "、".join(arc.traits[:4]) if arc.traits else "待补充"
        lines.append(f"- **{arc.name}**：{span}，{traits}")
        if arc.arc_summary:
            lines.append(f"  成长弧光：{arc.arc_summary}")
    lines.append("")

    # 改进建议
    if report.improvement_suggestions:
        lines.append("## 改进建议")
        seen = set()
        for s in report.improvement_suggestions:
            if s not in seen:
                lines.append(f"- {s}")
                seen.add(s)
        lines.append("")

    return "\n".join(lines)


def save_report(report: FinalReport, storage: Storage) -> tuple[str, str]:
    """保存Markdown和JSON报告，返回两个文件路径"""
    md = render_markdown(report)
    md_path = storage.save_text("output/report.md", md)
    json_path = storage.save_json("output/report.json", report.model_dump())
    return str(md_path), str(json_path)
