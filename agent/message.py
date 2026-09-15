"""单轮用户消息和 Agent 回复的处理。"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from .models import ItemRequest, OutfitItem, OutfitRecommendation, WardrobeQuery
from .query_expander import QueryExpansion


@dataclass(frozen=True)
class UserMessage:
    """用户发给 Agent 的一条消息。"""

    content: str


@dataclass(frozen=True)
class AgentMessage:
    """Agent 处理一条用户消息后返回的结果。"""

    content: str
    query: WardrobeQuery
    display_mode: Literal["outfit", "item_list"]
    items: tuple[OutfitItem, ...]
    item_requests: tuple[ItemRequest, ...] = ()
    query_expansions: tuple[QueryExpansion, ...] = ()


class MessageProcessor:
    """校验输入并把推荐结果整理成回复消息。"""

    def normalize(self, message: UserMessage) -> str:
        content = message.content.strip()
        if not content:
            raise ValueError("用户输入不能为空")
        return content

    def build_outfit_reply(
        self,
        query: WardrobeQuery,
        recommendation: OutfitRecommendation,
        item_requests: tuple[ItemRequest, ...] = (),
        query_expansions: tuple[QueryExpansion, ...] = (),
    ) -> AgentMessage:
        if recommendation.complete:
            lines = ["为你推荐以下搭配："]
        else:
            missing = "、".join(recommendation.missing)
            lines = [f"暂时无法组成完整搭配（缺少：{missing}），已有部件如下："]

        lines.extend(_format_item(item) for item in recommendation.items)
        if not recommendation.items:
            lines.append("没有找到符合条件的部件。")

        return AgentMessage(
            content="\n".join(lines),
            query=query,
            display_mode="outfit",
            items=recommendation.items,
            item_requests=item_requests,
            query_expansions=query_expansions,
        )

    def build_item_list_reply(
        self,
        query: WardrobeQuery,
        items: tuple[OutfitItem, ...],
        query_expansions: tuple[QueryExpansion, ...] = (),
    ) -> AgentMessage:
        if items:
            lines = [f"为你找到以下{items[0].type_zh}："]
            lines.extend(_format_item(item) for item in items)
        else:
            lines = ["没有找到符合条件的服装。"]

        return AgentMessage(
            content="\n".join(lines),
            query=query,
            display_mode="item_list",
            items=items,
            query_expansions=query_expansions,
        )


def _format_item(item: OutfitItem) -> str:
    return (
        f"- {item.type_zh}：{item.name}\n"
        f"  编号：{item.id}\n"
        f"  描述：{item.summary_zh or '暂无'}"
    )
