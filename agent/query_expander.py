"""为直接召回不足的抽象穿搭需求生成检索扩展。"""

from __future__ import annotations

import json
from dataclasses import dataclass

from .llm_client import DeepSeekClient, LLMClient
from .models import WardrobeQuery


EXPANSION_FIELDS = {
    "detail_query",
    "detail_keywords",
}


@dataclass(frozen=True)
class QueryExpansion:
    """仅用于检索的软条件，不参与 SQLite 硬过滤。"""

    detail_query: str
    detail_keywords: tuple[str, ...]


class QueryExpander:
    """为直接召回不足的查询补充具体视觉细节。"""

    def __init__(self, llm_client: LLMClient | None = None) -> None:
        self.llm_client = llm_client or DeepSeekClient()

    def expand(self, query: WardrobeQuery) -> QueryExpansion:
        if query.semantic_query is None:
            raise ValueError("缺少 semantic_query，无法扩展")

        response = self.llm_client.generate(
            self._build_system_prompt(),
            json.dumps(
                {
                    "semantic_query": query.semantic_query,
                    "keywords": query.keywords,
                    "explicit_constraints": {
                        "main_style": query.main_style,
                        "quality": query.quality,
                        "primary_color": query.primary_color,
                        "item_name": query.item_name,
                    },
                },
                ensure_ascii=False,
            ),
        )
        return self._parse_response(response)

    @staticmethod
    def _build_system_prompt() -> str:
        return """你是换装检索 Query Expander，只负责为直接召回不足的查询补充具体视觉细节。
必须只输出一个 JSON 对象，且只能包含 detail_query、detail_keywords 两个键。
颜色、风格和氛围等概括特征已经包含在 keywords 中，不要重复生成。
detail_keywords 只给出图片或服装描述中可能出现的纹样、剪裁、材质和装饰，例如“凤冠”“凤凰”“刺绣”“盘扣”。
detail_query 将这些细节关键词组织成适合文本向量检索的一句中文描述，并保留原始主题。
所有扩展内容都只是软偏好，不得修改 explicit_constraints，不得生成与用户明确条件冲突的颜色、属性或名称。
不要要求每个服装部件同时具有全部扩展特征，不要输出解释或 Markdown。"""

    @staticmethod
    def _parse_response(response: str) -> QueryExpansion:
        try:
            data = json.loads(response)
        except json.JSONDecodeError as error:
            raise ValueError("Query Expander 没有返回合法 JSON") from error

        if not isinstance(data, dict) or set(data) != EXPANSION_FIELDS:
            raise ValueError("Query Expander 必须且只能返回两个规定字段")

        detail_query = _parse_text(data["detail_query"], "detail_query")
        detail_keywords = _parse_keywords(data["detail_keywords"], "detail_keywords")
        return QueryExpansion(
            detail_query=detail_query,
            detail_keywords=detail_keywords,
        )


def _parse_text(value: object, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} 必须是非空字符串")
    return value.strip()


def _parse_keywords(value: object, field_name: str) -> tuple[str, ...]:
    if not isinstance(value, list) or any(
        not isinstance(keyword, str) or not keyword.strip() for keyword in value
    ):
        raise ValueError(f"{field_name} 必须是字符串数组")
    return tuple(dict.fromkeys(keyword.strip() for keyword in value))
