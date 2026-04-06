"""T06: 结果落盘与断点续传"""
from __future__ import annotations
import json
from pathlib import Path
from typing import Any

from .config import ARTIFACTS_DIR, OUTPUT_DIR, get_prompt_version, get_llm_config


def _cache_key_parts() -> dict[str, str]:
    return {
        "prompt_version": get_prompt_version(),
        "model": get_llm_config()["model"],
    }


def _meta_path(artifact_dir: Path) -> Path:
    return artifact_dir / "_meta.json"


def _check_meta(artifact_dir: Path) -> bool:
    """检查缓存元信息是否与当前配置匹配"""
    mp = _meta_path(artifact_dir)
    if not mp.exists():
        return False
    with open(mp, "r", encoding="utf-8") as f:
        stored = json.load(f)
    current = _cache_key_parts()
    return stored.get("prompt_version") == current["prompt_version"] and \
           stored.get("model") == current["model"]


def _write_meta(artifact_dir: Path) -> None:
    artifact_dir.mkdir(parents=True, exist_ok=True)
    with open(_meta_path(artifact_dir), "w", encoding="utf-8") as f:
        json.dump(_cache_key_parts(), f, ensure_ascii=False, indent=2)


class Storage:
    def __init__(self, base_dir: Path | None = None, resume: bool = False, force: bool = False):
        self.base = base_dir or ARTIFACTS_DIR
        self.output_dir = OUTPUT_DIR
        self.resume = resume
        self.force = force
        # 确保目录存在
        for sub in ["phase1_light", "phase1_deep", "phase2"]:
            (self.base / sub).mkdir(parents=True, exist_ok=True)
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def _dir(self, phase: str) -> Path:
        return self.base / phase

    def has_result(self, phase: str, chunk_id: int) -> bool:
        """检查某块是否已有合法缓存"""
        if self.force:
            return False
        d = self._dir(phase)
        if not _check_meta(d):
            return False
        fp = d / f"chunk_{chunk_id}.json"
        return fp.exists()

    def save_chunk_result(self, phase: str, chunk_id: int, data: dict) -> None:
        d = self._dir(phase)
        d.mkdir(parents=True, exist_ok=True)
        _write_meta(d)
        fp = d / f"chunk_{chunk_id}.json"
        with open(fp, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    def load_chunk_result(self, phase: str, chunk_id: int) -> dict | None:
        d = self._dir(phase)
        fp = d / f"chunk_{chunk_id}.json"
        if not fp.exists():
            return None
        with open(fp, "r", encoding="utf-8") as f:
            return json.load(f)

    def save_json(self, rel_path: str, data: Any) -> Path:
        """保存任意JSON到artifacts或output"""
        if rel_path.startswith("output/"):
            fp = self.output_dir / rel_path.removeprefix("output/")
        else:
            fp = self.base / rel_path
        fp.parent.mkdir(parents=True, exist_ok=True)
        with open(fp, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        return fp

    def save_text(self, rel_path: str, text: str) -> Path:
        if rel_path.startswith("output/"):
            fp = self.output_dir / rel_path.removeprefix("output/")
        else:
            fp = self.base / rel_path
        fp.parent.mkdir(parents=True, exist_ok=True)
        fp.write_text(text, encoding="utf-8")
        return fp

    def save_manifest(self, data: dict) -> None:
        self.save_json("chunks.json", data)

    def load_manifest(self) -> dict | None:
        fp = self.base / "chunks.json"
        if not fp.exists():
            return None
        with open(fp, "r", encoding="utf-8") as f:
            return json.load(f)
