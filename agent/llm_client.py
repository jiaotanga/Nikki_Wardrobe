"""DeepSeek LLM 客户端。"""

from __future__ import annotations

import os
from typing import Protocol

DEEPSEEK_BASE_URL = "https://api.deepseek.com"
DEFAULT_MODEL = "deepseek-v4-pro"


class LLMClient(Protocol):
    """意图解析工具需要的最小 LLM 接口。"""

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

        client = OpenAI(api_key=api_key, base_url=DEEPSEEK_BASE_URL)
        response = client.chat.completions.create(
            model=os.environ.get("DEEPSEEK_MODEL", DEFAULT_MODEL),
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            stream=False,
            reasoning_effort="high",
            extra_body={"thinking": {"type": "enabled"}},
        )

        content = response.choices[0].message.content
        if not content:
            raise RuntimeError("DeepSeek 返回了空内容")
        return content
