"""DeepSeek LLM 客户端。"""

from __future__ import annotations

import logging
import os
import time
from typing import Protocol

DEEPSEEK_BASE_URL = "https://api.deepseek.com"
DEFAULT_MODEL = "deepseek-v4-pro"
DEFAULT_TIMEOUT_SECONDS = 120.0
DEFAULT_REASONING_EFFORT = "low"

LOGGER = logging.getLogger(__name__)


class LLMClient(Protocol):
    """查询解析工具需要的最小 LLM 接口。"""

    def generate(self, system_prompt: str, user_prompt: str) -> str:
        ...


class DeepSeekClient:
    """通过 OpenAI 兼容接口调用 DeepSeek。"""

    def generate(self, system_prompt: str, user_prompt: str) -> str:
        from dotenv import load_dotenv
        from openai import OpenAI

        load_dotenv()
        api_key = os.environ.get("DEEPSEEK_API_KEY")
        if not api_key:
            raise RuntimeError("未找到环境变量 DEEPSEEK_API_KEY")

        timeout = float(
            os.environ.get("DEEPSEEK_TIMEOUT_SECONDS", DEFAULT_TIMEOUT_SECONDS)
        )
        model = os.environ.get("DEEPSEEK_MODEL", DEFAULT_MODEL)
        reasoning_effort = os.environ.get(
            "DEEPSEEK_REASONING_EFFORT",
            DEFAULT_REASONING_EFFORT,
        )
        client = OpenAI(
            api_key=api_key,
            base_url=DEEPSEEK_BASE_URL,
            timeout=timeout,
            max_retries=0,
        )
        started_at = time.perf_counter()
        LOGGER.info(
            "开始请求 DeepSeek，模型：%s，推理强度：%s，超时：%.0f 秒",
            model,
            reasoning_effort,
            timeout,
        )
        try:
            response = client.chat.completions.create(
                model=model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                stream=False,
                reasoning_effort=reasoning_effort,
                extra_body={"thinking": {"type": "enabled"}},
            )
        finally:
            LOGGER.info(
                "DeepSeek 请求结束，耗时：%.1f 秒",
                time.perf_counter() - started_at,
            )

        content = response.choices[0].message.content
        if not content:
            raise RuntimeError("DeepSeek 返回了空内容")
        return content
