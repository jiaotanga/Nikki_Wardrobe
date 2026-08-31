"""自然语言穿搭要求解析工具。"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from ..llm_client import DeepSeekClient, LLMClient
from ..models import Intent
from .recommender import DATABASE_PATH


INTENT_FIELDS = {"main_style", "quality", "primary_color", "style_label"}


class IntentParserTool:
    """把用户文本解析并校验为 Intent。"""

    name = "parse_intent"

    def __init__(
        self,
        llm_client: LLMClient | None = None,
        database_path: str | Path = DATABASE_PATH,
    ) -> None:
        self.llm_client = llm_client or DeepSeekClient()
        self.database_path = Path(database_path)

    def run(self, user_text: str) -> Intent:
        user_text = user_text.strip()
        if not user_text:
            raise ValueError("用户输入不能为空")

        allowed = self.load_allowed_values()
        response = self.llm_client.generate(
            self._build_system_prompt(allowed),
            user_text,
        )
        return self._parse_response(response, allowed)

    def load_allowed_values(self) -> dict[str, list[str]]:
        connection = sqlite3.connect(self.database_path)
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
                "item_type": [
                    row[0]
                    for row in connection.execute(
                        "SELECT DISTINCT type FROM items ORDER BY type"
                    )
                ],
            }
        finally:
            connection.close()

    @staticmethod
    def _build_system_prompt(allowed: dict[str, list[str]]) -> str:
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

    @staticmethod
    def _parse_response(
        llm_response: str,
        allowed: dict[str, list[str]],
    ) -> Intent:
        try:
            data = json.loads(llm_response)
        except json.JSONDecodeError as error:
            raise ValueError("LLM 没有返回合法 JSON") from error

        return IntentParserTool.parse_data(data, allowed)

    @staticmethod
    def parse_data(
        data: object,
        allowed: dict[str, list[str]],
    ) -> Intent:
        if not isinstance(data, dict) or set(data) != INTENT_FIELDS:
            raise ValueError("Intent 必须且只能包含四个规定字段")
        if data["quality"] not in (None, 3, 4, 5):
            raise ValueError("quality 只能是 3、4、5 或 null")

        for field in ("main_style", "primary_color", "style_label"):
            value = data[field]
            if value is not None and value not in allowed[field]:
                raise ValueError(f"{field} 不是数据库中的合法值：{value}")

        return Intent(**data)
