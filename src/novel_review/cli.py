"""T01: CLI入口 — 串联全流程"""
from __future__ import annotations
import argparse
import asyncio
import sys
from pathlib import Path

from rich.console import Console
from rich.panel import Panel

from . import __version__
from .config import ARTIFACTS_DIR, OUTPUT_DIR
from .preprocessor import read_text, build_chunks
from .llm_client import LLMClient
from .storage import Storage
from .progress import ProgressTracker
from .analyzer_phase1_light import run_phase1_light
from .analyzer_phase1_deep import run_phase1_deep
from .analyzer_phase2 import run_phase2
from .analyzer_phase3 import run_phase3
from .reporter import save_report, render_markdown

console = Console()


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        prog="novel-review",
        description=f"小说多维度自动评价工具 v{__version__}",
    )
    p.add_argument("--input", "-i", required=True, help="输入txt文件路径")
    p.add_argument("--output", "-o", default=str(OUTPUT_DIR), help="输出目录")
    p.add_argument("--resume", action="store_true", help="断点续传，跳过已完成的块")
    p.add_argument("--force", action="store_true", help="强制重新分析所有块")
    p.add_argument("--mode", choices=["full", "auto"], default="auto",
                   help="full=全量精读 auto=根据字数自动选择")
    return p.parse_args()


async def run_pipeline(args: argparse.Namespace) -> None:
    input_path = Path(args.input)
    if not input_path.exists():
        console.print(f"[red]文件不存在: {input_path}[/red]")
        sys.exit(1)

    console.print(Panel(
        f"[bold]Novel Review Tool v{__version__}[/bold]\n"
        f"输入: {input_path.name}\n"
        f"模式: {args.mode}",
        title="开始分析",
    ))

    # ── Phase0: 预处理 ──
    console.print("\n[bold yellow]Phase 0:[/bold yellow] 文本预处理与分块...")
    text = read_text(input_path)
    manifest = build_chunks(text, input_path)
    title = input_path.stem  # 用文件名作为书名

    console.print(f"  总字数: {manifest.total_chars:,}")
    console.print(f"  分块数: {manifest.total_chunks}")

    # 按书名隔离artifacts和output
    book_artifacts = ARTIFACTS_DIR / title
    book_output = OUTPUT_DIR / title
    storage = Storage(
        base_dir=book_artifacts,
        resume=args.resume,
        force=args.force,
    )
    storage.output_dir = book_output
    book_output.mkdir(parents=True, exist_ok=True)
    storage.save_manifest(manifest.model_dump())

    # 进度追踪器
    tracker = ProgressTracker(book_output)

    force_full = args.mode == "full"

    # ── Phase1 Light ──
    console.print(f"\n[bold yellow]Phase 1a:[/bold yellow] 轻筛分析 ({manifest.total_chunks}块)...")
    llm = LLMClient()
    light_results = await run_phase1_light(manifest, llm, storage, tracker=tracker)
    console.print(f"  轻筛完成，LLM调用 {llm.total_calls} 次")

    # ── Phase1 Deep ──
    from .analyzer_phase1_deep import select_deep_chunks
    deep_ids = select_deep_chunks(manifest, light_results, force_full=force_full)
    console.print(f"\n[bold yellow]Phase 1b:[/bold yellow] 精读分析 ({len(deep_ids)}/{manifest.total_chunks}块)...")
    deep_results = await run_phase1_deep(manifest, light_results, llm, storage, tracker=tracker)
    console.print(f"  精读完成，LLM调用 {llm.total_calls} 次")

    # ── Phase2 ──
    console.print(f"\n[bold yellow]Phase 2:[/bold yellow] 跨块综合分析...")
    tracker.start_phase("Phase2 跨块综合", 1)
    analysis = run_phase2(light_results, deep_results, storage)
    tracker.advance(f"{len(analysis.character_arcs)}个角色, {len(analysis.foreshadowing_pairs)}条伏笔")
    tracker.finish_phase()
    console.print(f"  人物: {len(analysis.character_arcs)} 个主要角色")
    console.print(f"  伏笔: {len(analysis.foreshadowing_pairs)} 条")

    # ── Phase3 ──
    console.print(f"\n[bold yellow]Phase 3:[/bold yellow] 最终评价生成...")
    tracker.start_phase("Phase3 最终评价", 1)
    report = await run_phase3(
        analysis, light_results, deep_results, llm,
        total_chars=manifest.total_chars,
        title=title,
    )
    tracker.advance(f"总分{report.weighted_total}")
    tracker.finish_phase()

    # ── 输出 ──
    md_path, json_path = save_report(report, storage)
    console.print(f"\n[bold green]完成！[/bold green]")
    console.print(f"  Markdown报告: {md_path}")
    console.print(f"  JSON报告: {json_path}")
    tracker.finish(f"总分{report.weighted_total}, {llm.stats()}")
    console.print(f"\n[dim]LLM统计: {llm.stats()}[/dim]")

    # 打印报告摘要
    console.print("\n" + "=" * 60)
    console.print(Panel(
        f"[bold]{report.one_line_summary}[/bold]\n\n"
        f"总分: {report.weighted_total}/10  "
        f"推荐: {'★' * report.recommendation_stars}{'☆' * (5 - report.recommendation_stars)}",
        title=f"《{title}》评价摘要",
    ))


def main() -> None:
    args = parse_args()
    asyncio.run(run_pipeline(args))


if __name__ == "__main__":
    main()
