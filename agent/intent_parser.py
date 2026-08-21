"""用户自然语言到 Intent 的外层调用流程。"""

from __future__ import annotations

import json
import sqlite3
import sys

if __package__:
    from .llm_client import call_llm_once
    from .recommender import DATABASE_PATH, Intent
else:  # 允许直接运行：python agent\intent_parser.py
    from llm_client import call_llm_once
    from recommender import DATABASE_PATH, Intent


INTENT_FIELDS = {"main_style", "quality", "primary_color", "style_label"}


def _load_allowed_values() -> dict[str, list[str]]:
    """从数据库读取 LLM 可以使用的合法标签。"""
    connection = sqlite3.connect(DATABASE_PATH)
    try:
        return {
            "main_style": [
                row[0]
                for row in connection.execute(
                    "SELECT DISTINCT main_style_zh FROM items ORDER BY main_style_zh"
                )
            ],
            "primary_color": [
                row[0]
                for row in connection.execute(
                    """
                    SELECT DISTINCT family FROM item_colors
                    WHERE role = 'primary' ORDER BY family
                    """
                )
            ],
            "style_label": [
                row[0]
                for row in connection.execute("SELECT name FROM labels ORDER BY name")
            ],
        }
    finally:
        connection.close()


def _build_system_prompt(allowed: dict[str, list[str]]) -> str:
    """告诉 LLM 固定格式和允许使用的值。"""
    return f"""你是换装需求意图解析器，只负责把用户的一句话转换为 JSON。
必须只输出一个 JSON 对象，不要解释，不要使用 Markdown。
JSON 必须且只能包含 main_style、quality、primary_color、style_label 四个键。
用户没有指定的值必须是 null。
quality 只能是整数 3、4、5；只有用户明确提到星级时才填写。
primary_color 只有用户明确提到颜色时才填写。
main_style 和 style_label 可以根据相近语义选择；没有合适值就填 null。
main_style 只能从这里选择：{json.dumps(allowed['main_style'], ensure_ascii=False)}
primary_color 只能从这里选择：{json.dumps(allowed['primary_color'], ensure_ascii=False)}
style_label 只能从这里选择：{json.dumps(allowed['style_label'], ensure_ascii=False)}"""


def request_intent_analysis(user_text: str) -> str:
    """把一句用户输入和数据库合法标签发送给 LLM。"""
    user_text = user_text.strip()
    if not user_text:
        raise ValueError("用户输入不能为空")
    allowed = _load_allowed_values()
    return call_llm_once(_build_system_prompt(allowed), user_text)


def parse_intent_response(llm_response: str) -> Intent:
    """校验 LLM 返回的 JSON，并转换为 Intent。"""
    try:
        data = json.loads(llm_response)
    except json.JSONDecodeError as error:
        raise ValueError("LLM 没有返回合法 JSON") from error

    if not isinstance(data, dict) or set(data) != INTENT_FIELDS:
        raise ValueError("Intent 必须且只能包含四个规定字段")

    allowed = _load_allowed_values()
    if data["quality"] not in (None, 3, 4, 5):
        raise ValueError("quality 只能是 3、4、5 或 null")

    for field in ("main_style", "primary_color", "style_label"):
        value = data[field]
        if value is not None and value not in allowed[field]:
            raise ValueError(f"{field} 不是数据库中的合法值：{value}")

    return Intent(**data)


def main() -> int:
    """读取一句用户输入，完成一次调用并打印 Intent。"""
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")

    user_text = input("请输入搭配要求：").strip()
    try:
        llm_response = request_intent_analysis(user_text)
        intent = parse_intent_response(llm_response)
    except (ValueError, RuntimeError, sqlite3.Error) as error:
        print(f"解析失败：{error}", file=sys.stderr)
        return 1

    print("解析得到的 Intent：")
    print(intent)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
