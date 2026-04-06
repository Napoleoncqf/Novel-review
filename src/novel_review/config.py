"""T03: 配置加载 — .env + dimensions.yaml"""
from __future__ import annotations
import os
import sys
from pathlib import Path
from typing import Any

import yaml
from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
CONFIG_DIR = PROJECT_ROOT / "config"
ARTIFACTS_DIR = PROJECT_ROOT / "artifacts"
OUTPUT_DIR = PROJECT_ROOT / "output"


def _load_env() -> None:
    env_path = PROJECT_ROOT / ".env"
    if env_path.exists():
        load_dotenv(env_path)


def get_llm_config() -> dict[str, Any]:
    _load_env()
    provider = os.getenv("LLM_PROVIDER", "auto")

    # Gemini优先（如果设置了GEMINI_API_KEY）
    gemini_key = os.getenv("GEMINI_API_KEY")
    llm_key = os.getenv("LLM_API_KEY")

    if provider == "gemini" or (provider == "auto" and gemini_key):
        if not gemini_key:
            print("[ERROR] GEMINI_API_KEY 未设置", file=sys.stderr)
            sys.exit(1)
        return {
            "api_key": gemini_key,
            "base_url": "https://generativelanguage.googleapis.com/v1beta/openai/",
            "model": os.getenv("GEMINI_MODEL", "gemini-2.5-flash"),
            "temperature": 0.3,
            "max_concurrent": 5,
        }

    # 默认：SiliconFlow / 其他OpenAI兼容API
    api_key = llm_key
    base_url = os.getenv("LLM_BASE_URL")
    model = os.getenv("LLM_MODEL", "deepseek-ai/DeepSeek-V3")
    if not api_key:
        print("[ERROR] LLM_API_KEY 或 GEMINI_API_KEY 至少设置一个", file=sys.stderr)
        sys.exit(1)
    return {
        "api_key": api_key,
        "base_url": base_url,
        "model": model,
        "temperature": 0.3,
        "max_concurrent": 3,
    }


def load_dimensions(path: Path | None = None) -> dict[str, Any]:
    path = path or CONFIG_DIR / "dimensions.yaml"
    with open(path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f)
    return data


def get_all_dimensions(dim_data: dict | None = None) -> list[dict]:
    if dim_data is None:
        dim_data = load_dimensions()
    dims = dim_data.get("dimensions", {})
    return dims.get("core", []) + dims.get("auxiliary", [])


def get_prompt_version(dim_data: dict | None = None) -> str:
    if dim_data is None:
        dim_data = load_dimensions()
    return dim_data.get("prompt_version", "v1")


def build_rubric_text(dim_data: dict | None = None) -> str:
    all_dims = get_all_dimensions(dim_data)
    lines = []
    for d in all_dims:
        lines.append(f"## {d['name']}（权重{d['weight']}）")
        lines.append(f"  子维度：{'、'.join(d['sub_aspects'])}")
        for band, desc in d.get("rubric", {}).items():
            lines.append(f"  [{band}分] {desc}")
        lines.append("")
    return "\n".join(lines)
