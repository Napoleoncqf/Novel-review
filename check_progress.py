"""查看运行进度 — python check_progress.py [书名]"""
import json
import sys
from pathlib import Path

def show(book: str = ""):
    output_dir = Path("output")
    if book:
        p = output_dir / book / "progress.json"
    else:
        # 找最近的 progress.json
        candidates = sorted(output_dir.glob("*/progress.json"), key=lambda f: f.stat().st_mtime, reverse=True)
        if not candidates:
            print("没有找到 progress.json")
            return
        p = candidates[0]
        book = p.parent.name

    if not p.exists():
        print(f"进度文件不存在: {p}")
        return

    with open(p, encoding="utf-8") as f:
        d = json.load(f)

    elapsed = d.get("elapsed_sec", 0)
    mins, secs = divmod(int(elapsed), 60)

    print(f"═══ 《{book}》分析进度 ═══")
    print(f"  阶段: {d['phase']}")
    print(f"  进度: {d['phase_progress']}")
    print(f"  当前: {d['detail']}")
    print(f"  耗时: {mins}分{secs}秒")
    print(f"  错误: {d['errors']}个")
    print(f"  已完成阶段: {', '.join(d['phases_done']) or '无'}")

if __name__ == "__main__":
    show(sys.argv[1] if len(sys.argv) > 1 else "")
