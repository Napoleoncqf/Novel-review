"""实时进度追踪 — 写入 progress.json 供外部查看"""
from __future__ import annotations
import json
import time
from pathlib import Path


class ProgressTracker:
    def __init__(self, output_path: Path):
        self.path = output_path / "progress.json"
        self.start_time = time.time()
        self.data = {
            "phase": "",
            "phase_progress": "",
            "current": 0,
            "total": 0,
            "detail": "",
            "elapsed_sec": 0,
            "phases_done": [],
            "errors": 0,
        }
        self._write()

    def start_phase(self, phase: str, total: int) -> None:
        self.data["phase"] = phase
        self.data["current"] = 0
        self.data["total"] = total
        self.data["detail"] = ""
        self._update_progress()
        self._write()

    def advance(self, detail: str = "", error: bool = False) -> None:
        self.data["current"] += 1
        self.data["detail"] = detail
        if error:
            self.data["errors"] += 1
        self._update_progress()
        self._write()

    def finish_phase(self) -> None:
        self.data["phases_done"].append(self.data["phase"])
        self._update_progress()
        self._write()

    def finish(self, summary: str = "") -> None:
        self.data["phase"] = "完成"
        self.data["detail"] = summary
        self._update_progress()
        self._write()

    def _update_progress(self) -> None:
        self.data["elapsed_sec"] = round(time.time() - self.start_time, 1)
        total = self.data["total"]
        current = self.data["current"]
        if total > 0:
            pct = round(current / total * 100, 1)
            self.data["phase_progress"] = f"{current}/{total} ({pct}%)"
        else:
            self.data["phase_progress"] = ""

    def _write(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.path, "w", encoding="utf-8") as f:
            json.dump(self.data, f, ensure_ascii=False, indent=2)
