"""自然语言衣橱查询解析工具。"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from ..llm_client import DeepSeekClient, LLMClient
from ..models import WardrobeQuery
from .recommender import DATABASE_PATH


QUERY_FIELDS = {
    "main_style",
    "quality",
    "primary_color",
    "item_name",
    "semantic_query",
    "keywords",
}


class WardrobeQueryParserTool:
    """把用户文本解析并校验为 WardrobeQuery。"""

    name = "parse_wardrobe_query"

    def __init__(
        self,
        llm_client: LLMClient | None = None,
        database_path: str | Path = DATABASE_PATH,
    ) -> None:
        self.llm_client = llm_client or DeepSeekClient()
        self.database_path = Path(database_path)

    def run(self, user_text: str) -> WardrobeQuery:
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
        return """你是换装需求查询解析器，只负责把用户的一句话转换为 JSON。
必须只输出一个 JSON 对象，不要解释，不要使用 Markdown。
""" + WardrobeQueryParserTool.build_query_instructions(allowed)

    @staticmethod
    def build_query_instructions(allowed: dict[str, list[str]]) -> str:
        return f"""查询 JSON 对象必须且只能包含 main_style、quality、primary_color、item_name、semantic_query、keywords 六个键。
除 keywords 外，用户没有指定的值必须是 null；keywords 没有内容时必须是空数组。
quality 只能是整数 3、4、5；只有用户明确提到星级或品质时才填写，“最高品质”表示 5，其他模糊说法不得推断。
main_style 是部件的属性标签，不代表视觉风格；只有用户明确说“主属性”或“属性”为某个合法值时才填写，不得根据“古风、优雅、可爱”等描述推断。
primary_color 只有用户明确提到颜色时才填写；如果原始颜色比合法值更具体，应映射到所属的合法标准色，并将原始细分颜色保留在 semantic_query 和 keywords 中。
item_name 只有用户明确指定某个部件的确切名称时才原样填写，不得把“红色连衣裙”等描述当作名称。
semantic_query 使用一句话总结去掉动作和以上硬条件后，用户仍然想要的风格、外观或细节描述；硬条件归一化时丢失的细节也必须保留，没有则填 null。
keywords 必须从 semantic_query 中提取，只保留具有明确视觉指向的最小语义词，去掉“装饰、图案、设计、元素、风格、感觉”等泛化词，但不要拆分“双马尾、蝴蝶结、玫瑰金”等完整概念；不得扩展或编造，没有则填空数组。
只要 keywords 不是空数组，semantic_query 就不能是 null；semantic_query 是 null 时，keywords 必须是空数组。
例如“帮我搜索有珍珠装饰的发型”应解析为 semantic_query="有珍珠装饰"、keywords=["珍珠"]。
例如“请给我一套红色的古风搭配”应解析为 main_style=null、quality=null、primary_color="红色"、semantic_query="古风"、keywords=["古风"]。
例如“请给我一套最高品质、主属性为典雅的搭配”应解析为 main_style="典雅"、quality=5、primary_color=null、semantic_query=null、keywords=[]。
例如“查询名为芊芊知夏的部件”应解析为 item_name="芊芊知夏"，其他查询条件为 null，keywords=[]。
main_style 只能从这里选择：{json.dumps(allowed['main_style'], ensure_ascii=False)}
primary_color 只能从这里选择：{json.dumps(allowed['primary_color'], ensure_ascii=False)}"""

    @staticmethod
    def _parse_response(
        llm_response: str,
        allowed: dict[str, list[str]],
    ) -> WardrobeQuery:
        try:
            data = json.loads(llm_response)
        except json.JSONDecodeError as error:
            raise ValueError("LLM 没有返回合法 JSON") from error

        return WardrobeQueryParserTool.parse_data(data, allowed)

    @staticmethod
    def parse_data(
        data: object,
        allowed: dict[str, list[str]],
    ) -> WardrobeQuery:
        if not isinstance(data, dict) or set(data) != QUERY_FIELDS:
            raise ValueError("WardrobeQuery 必须且只能包含六个规定字段")
        if data["quality"] not in (None, 3, 4, 5):
            raise ValueError("quality 只能是 3、4、5 或 null")

        if data["main_style"] is not None and data["main_style"] not in allowed[
            "main_style"
        ]:
            raise ValueError(f"main_style 不是数据库中的合法值：{data['main_style']}")
        if data["primary_color"] is not None and data["primary_color"] not in allowed[
            "primary_color"
        ]:
            raise ValueError(
                f"primary_color 不是数据库中的合法值：{data['primary_color']}"
            )

        item_name = data["item_name"]
        if item_name is not None and (
            not isinstance(item_name, str) or not item_name.strip()
        ):
            raise ValueError("item_name 必须是非空字符串或 null")

        semantic_query = data["semantic_query"]
        if semantic_query is not None and (
            not isinstance(semantic_query, str) or not semantic_query.strip()
        ):
            raise ValueError("semantic_query 必须是非空字符串或 null")

        keywords = data["keywords"]
        if not isinstance(keywords, list) or any(
            not isinstance(keyword, str) or not keyword.strip()
            for keyword in keywords
        ):
            raise ValueError("keywords 必须是字符串数组")
        if keywords and semantic_query is None:
            raise ValueError("keywords 有内容时 semantic_query 不能是 null")

        return WardrobeQuery(
            main_style=data["main_style"],
            quality=data["quality"],
            primary_color=data["primary_color"],
            item_name=item_name,
            semantic_query=semantic_query,
            keywords=tuple(keywords),
        )
