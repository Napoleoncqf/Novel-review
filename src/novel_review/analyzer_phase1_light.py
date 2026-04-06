"""T07: Phase1轻筛分析器"""
from __future__ import annotations
import json

from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn

from .models import ChunkManifest, LightResult
from .llm_client import LLMClient
from .storage import Storage
from .normalize import normalize_light_data
from .progress import ProgressTracker

SYSTEM_PROMPT = """\
你是一个小说文本分析助手。请对给定的小说片段做轻量级筛选分析。
只输出合法JSON，不要输出Markdown包裹或任何额外文字。"""

USER_TEMPLATE = """\
请分析以下小说片段（第{chunk_id}块，字符范围{char_range}，章节：{chapter_ref}）。

前文摘要：
{previous_summary}

当前片段：
{chunk_text}

请输出JSON，包含以下字段：
- plot_events: 本块关键情节事件列表（string数组）
- characters_present: 出场人物列表（string数组）
- plot_progression: 是否推进主线（格式："yes: 原因" 或 "no: 原因"）
- state_changes: 角色/关系/设定的状态变化（对象数组，每项含entity和change）
- pacing_score: 节奏紧凑度（1-5整数，1最松散5最紧凑）
- candidate_flags: 标签数组，可选值包括：高潮、设定变更、关系突变、可疑缺陷、转折点、情感高峰"""


async def run_phase1_light(
    manifest: ChunkManifest,
    llm: LLMClient,
    storage: Storage,
    tracker: ProgressTracker | None = None,
) -> list[LightResult]:
    results: list[LightResult] = []
    prev_summary = "（开篇，无前文）"

    if tracker:
        tracker.start_phase("Phase1a 轻筛", len(manifest.chunks))

    with Progress(
        SpinnerColumn(),
        TextColumn("[bold blue]Phase1 轻筛"),
        BarColumn(),
        TextColumn("{task.completed}/{task.total}"),
    ) as progress:
        task = progress.add_task("轻筛", total=len(manifest.chunks))

        for chunk in manifest.chunks:
            cid = chunk.chunk_id

            # 断点续传：检查缓存
            if storage.has_result("phase1_light", cid):
                cached = storage.load_chunk_result("phase1_light", cid)
                if cached:
                    cached = normalize_light_data(cached)
                    lr = LightResult(**cached)
                    results.append(lr)
                    prev_summary = _make_summary(lr)
                    progress.advance(task)
                    continue

            user_msg = USER_TEMPLATE.format(
                chunk_id=cid,
                char_range=f"{chunk.char_range[0]}-{chunk.char_range[1]}",
                chapter_ref=chunk.chapter_ref or f"块{cid}",
                previous_summary=prev_summary,
                chunk_text=chunk.text[:8000],  # 安全截断
            )

            try:
                data = await llm.ask_json(SYSTEM_PROMPT, user_msg)
                data = normalize_light_data(data)
                data["chunk_id"] = cid
                data["char_range"] = list(chunk.char_range)
                data["chapter_ref"] = chunk.chapter_ref
                lr = LightResult(**data)
            except Exception as e:
                # 解析失败时给默认值
                lr = LightResult(
                    chunk_id=cid,
                    char_range=chunk.char_range,
                    chapter_ref=chunk.chapter_ref,
                    plot_events=[f"[解析失败: {e}]"],
                    pacing_score=3,
                )

            storage.save_chunk_result("phase1_light", cid, lr.model_dump())
            results.append(lr)
            prev_summary = _make_summary(lr)
            progress.advance(task)
            if tracker:
                tracker.advance(f"块{cid} {lr.chapter_ref}")

    if tracker:
        tracker.finish_phase()
    return results


def _make_summary(lr: LightResult) -> str:
    events = "；".join(lr.plot_events[:3]) if lr.plot_events else "无重要事件"
    chars = "、".join(lr.characters_present[:5]) if lr.characters_present else ""
    return f"[{lr.chapter_ref}] {events}。出场人物：{chars}"
