"""T08: Phase1精读分析器"""
from __future__ import annotations

from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn

from .models import ChunkManifest, LightResult, DeepResult
from .llm_client import LLMClient
from .storage import Storage
from .config import build_rubric_text
from .normalize import normalize_deep_data
from .progress import ProgressTracker

SYSTEM_PROMPT = """\
你是一位专业的小说文学评论分析师。请对给定的小说片段做深度分析。
为每个重要判断提供证据（原文引用<=30字）。
只输出合法JSON，不要输出Markdown包裹或任何额外文字。"""

USER_TEMPLATE = """\
请深度分析以下小说片段（第{chunk_id}块，字符范围{char_range}，章节：{chapter_ref}）。

前文摘要：
{previous_summary}

当前片段：
{chunk_text}

评分参考标准：
{rubric}

请输出JSON，包含以下字段：
- plot_events: 关键情节事件列表
- characters_present: 出场人物及行为/情感状态
- emotional_tone: 情绪基调（如：紧张、平静、悲伤、热血、压抑、温馨等）
- worldbuilding_elements: 新出现的设定要素
- foreshadowing: 伏笔列表，每项含description、status（planted/resolved）。planted=本块新埋设的伏笔，resolved=本块回收了前文某条伏笔（description应与原伏笔描述尽量一致）。重要：1）仅记录需要后文明确回收的重要伏笔（悬念、谜团、契诃夫之枪），不要把普通暗示当伏笔；2）仔细检查前文摘要中提到的悬念是否在本块得到解答，如果是请标记为resolved
- pacing_score: 节奏紧凑度（1-5）
- information_density: 信息增量密度（1-5，1最稀疏5最密集）
- notable_writing: 文笔亮点或问题列表（每项引用原文<=30字并说明）
- evidence: 证据列表，每项含quote(<=30字)、char_range(两个整数)、chapter_ref、reason
- defects_detected: 触发的缺陷规则ID列表（可选：D01龙傲天 D02金手指过度 D03感情线突兀 D04节奏塌陷 D05人设崩塌 D06设定遗忘 D07注水严重 D08伏笔断裂）"""


def select_deep_chunks(
    manifest: ChunkManifest,
    light_results: list[LightResult],
    force_full: bool = False,
) -> list[int]:
    """选择需要精读的块。短篇全部精读，长篇按策略选择。"""
    total = len(manifest.chunks)
    if force_full or manifest.total_chars < 500000:
        # 短中篇：全量精读
        return list(range(total))

    # 长篇：按抽样策略，目标精读30-50%
    selected = set()
    # 前3块 + 后3块（必选）
    for i in range(min(3, total)):
        selected.add(i)
    for i in range(max(0, total - 3), total):
        selected.add(i)

    # 最高pacing + plot_progression的块（取top 20%）
    scored = [(lr.chunk_id, lr.pacing_score) for lr in light_results
              if lr.pacing_score >= 4 and lr.plot_progression.lower().startswith("yes")]
    scored.sort(key=lambda x: x[1], reverse=True)
    top_n = max(total // 5, 10)
    for cid, _ in scored[:top_n]:
        selected.add(cid)

    # 有强关键标签的块（仅选"高潮"和"转折点"，不选宽泛标签）
    for lr in light_results:
        flags = [str(f) for f in lr.candidate_flags]
        if any(k in " ".join(flags) for k in ["高潮", "转折点"]):
            selected.add(lr.chunk_id)

    # 有重大状态变化的块
    for lr in light_results:
        if len(lr.state_changes) >= 2:
            selected.add(lr.chunk_id)

    # 等距抽样：每10块至少1块
    for i in range(0, total, 10):
        selected.add(i)

    # 上限：不超过总块数的50%
    if len(selected) > total // 2:
        # 保留必选（前3+后3+等距），其余按pacing排序截断
        must_keep = set()
        for i in range(min(3, total)):
            must_keep.add(i)
        for i in range(max(0, total - 3), total):
            must_keep.add(i)
        for i in range(0, total, 10):
            must_keep.add(i)
        optional = sorted(selected - must_keep,
                          key=lambda cid: next((lr.pacing_score for lr in light_results if lr.chunk_id == cid), 0),
                          reverse=True)
        budget = total // 2 - len(must_keep)
        selected = must_keep | set(optional[:max(budget, 0)])

    return sorted(selected)


async def run_phase1_deep(
    manifest: ChunkManifest,
    light_results: list[LightResult],
    llm: LLMClient,
    storage: Storage,
    tracker: ProgressTracker | None = None,
) -> list[DeepResult]:
    deep_ids = select_deep_chunks(manifest, light_results)
    rubric = build_rubric_text()
    results: list[DeepResult] = []

    if tracker:
        tracker.start_phase("Phase1b 精读", len(deep_ids))

    # 构建light摘要映射
    light_map = {lr.chunk_id: lr for lr in light_results}

    with Progress(
        SpinnerColumn(),
        TextColumn("[bold green]Phase1 精读"),
        BarColumn(),
        TextColumn("{task.completed}/{task.total}"),
    ) as progress:
        task = progress.add_task("精读", total=len(deep_ids))
        prev_summary = "（开篇，无前文）"

        for cid in deep_ids:
            # 断点续传
            if storage.has_result("phase1_deep", cid):
                cached = storage.load_chunk_result("phase1_deep", cid)
                if cached:
                    cached = normalize_deep_data(cached)
                    dr = DeepResult(**cached)
                    results.append(dr)
                    prev_summary = _deep_summary(dr)
                    progress.advance(task)
                    continue

            chunk = manifest.chunks[cid]
            user_msg = USER_TEMPLATE.format(
                chunk_id=cid,
                char_range=f"{chunk.char_range[0]}-{chunk.char_range[1]}",
                chapter_ref=chunk.chapter_ref or f"块{cid}",
                previous_summary=prev_summary,
                chunk_text=chunk.text[:8000],
                rubric=rubric[:3000],  # 截断避免超长
            )

            try:
                data = await llm.ask_json(SYSTEM_PROMPT, user_msg)
                data = normalize_deep_data(data)
                data["chunk_id"] = cid
                data["char_range"] = list(chunk.char_range)
                data["chapter_ref"] = chunk.chapter_ref
                dr = DeepResult(**data)
            except Exception as e:
                dr = DeepResult(
                    chunk_id=cid,
                    char_range=chunk.char_range,
                    chapter_ref=chunk.chapter_ref,
                    plot_events=[f"[解析失败: {e}]"],
                )

            storage.save_chunk_result("phase1_deep", cid, dr.model_dump())
            results.append(dr)
            prev_summary = _deep_summary(dr)
            progress.advance(task)
            if tracker:
                tracker.advance(f"块{cid} {dr.chapter_ref}")

    if tracker:
        tracker.finish_phase()

    # 更新manifest中的analysis_depth
    deep_set = set(deep_ids)
    for c in manifest.chunks:
        c.analysis_depth = "deep" if c.chunk_id in deep_set else "light"

    return results


def _deep_summary(dr: DeepResult) -> str:
    events = "；".join(dr.plot_events[:3]) if dr.plot_events else "无重要事件"
    tone = dr.emotional_tone or "未知"
    return f"[{dr.chapter_ref}] {events}。情绪：{tone}"
