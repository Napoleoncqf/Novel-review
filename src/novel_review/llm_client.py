"""T05: LLM调用封装 — OpenAI兼容API + 重试 + 并发控制"""
from __future__ import annotations
import asyncio
import json
import time
from typing import Any

from openai import AsyncOpenAI
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

from .config import get_llm_config


class LLMClient:
    def __init__(self, config: dict[str, Any] | None = None):
        cfg = config or get_llm_config()
        self.client = AsyncOpenAI(
            api_key=cfg["api_key"],
            base_url=cfg["base_url"],
            timeout=120.0,  # 单次请求120秒超时
        )
        self.model = cfg["model"]
        self.temperature = cfg.get("temperature", 0.3)
        self._semaphore = asyncio.Semaphore(cfg.get("max_concurrent", 3))
        # 统计
        self.total_prompt_tokens = 0
        self.total_completion_tokens = 0
        self.total_calls = 0
        self.total_time = 0.0

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=2, min=4, max=60),
        retry=retry_if_exception_type((ConnectionError, TimeoutError, OSError)),
        reraise=True,
    )
    async def _call(self, system: str, user: str) -> str:
        async with self._semaphore:
            t0 = time.time()
            resp = await self.client.chat.completions.create(
                model=self.model,
                temperature=self.temperature,
                messages=[
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
            )
            elapsed = time.time() - t0
            self.total_time += elapsed
            self.total_calls += 1
            usage = resp.usage
            if usage:
                self.total_prompt_tokens += usage.prompt_tokens
                self.total_completion_tokens += usage.completion_tokens
            return resp.choices[0].message.content or ""

    async def ask_json(self, system: str, user: str) -> dict:
        """调用LLM并解析JSON响应"""
        raw = await self._call(system, user)
        raw = raw.strip()
        # 尝试从markdown代码块中提取JSON
        if raw.startswith("```"):
            lines = raw.split("\n")
            start = 1
            # 跳过```json等语言标签行
            if start < len(lines) and lines[start].strip().lower() in ("json", "jsonc", ""):
                start += 1
            end = len(lines)
            for i in range(len(lines) - 1, 0, -1):
                if lines[i].strip().startswith("```"):
                    end = i
                    break
            raw = "\n".join(lines[start:end])
        # 尝试找到第一个{和最后一个}之间的内容
        first_brace = raw.find("{")
        last_brace = raw.rfind("}")
        if first_brace >= 0 and last_brace > first_brace:
            raw = raw[first_brace:last_brace + 1]
        return json.loads(raw)

    async def ask_text(self, system: str, user: str) -> str:
        return await self._call(system, user)

    def stats(self) -> dict:
        return {
            "total_calls": self.total_calls,
            "prompt_tokens": self.total_prompt_tokens,
            "completion_tokens": self.total_completion_tokens,
            "total_tokens": self.total_prompt_tokens + self.total_completion_tokens,
            "total_time_s": round(self.total_time, 1),
        }
