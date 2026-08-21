"""DeepSeek API 的最小单次通信封装。"""

from __future__ import annotations

import os

from dotenv import load_dotenv
from openai import OpenAI


DEEPSEEK_BASE_URL = "https://api.deepseek.com"
DEFAULT_MODEL = "deepseek-v4-pro"


def call_llm_once(system_prompt: str, user_prompt: str) -> str:
    """向 DeepSeek 发送一组 system/user 消息并返回文本回复。"""
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
