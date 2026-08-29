"""单轮用户消息和 Agent 回复的处理。"""

from __future__ import annotations

from dataclasses import dataclass

from .models import Intent, OutfitRecommendation


@dataclass(frozen=True)
class UserMessage:
    """用户发给 Agent 的一条消息。"""

    content: str


@dataclass(frozen=True)
class AgentMessage:
    """Agent 处理一条用户消息后返回的结果。"""

    content: str
    intent: Intent
    recommendation: OutfitRecommendation


class MessageProcessor:
    """校验输入并把推荐结果整理成回复消息。"""

    def normalize(self, message: UserMessage) -> str:
        content = message.content.strip()
        if not content:
            raise ValueError("用户输入不能为空")
        return content

    def build_reply(
        self,
        intent: Intent,
        recommendation: OutfitRecommendation,
    ) -> AgentMessage:
        if recommendation.complete:
            lines = ["为你推荐以下搭配："]
        else:
            missing = "、".join(recommendation.missing)
            lines = [f"暂时无法组成完整搭配（缺少：{missing}），已有部件如下："]

        lines.extend(
            f"- {item.type_zh}：{item.name}" for item in recommendation.items
        )
        if not recommendation.items:
            lines.append("没有找到符合条件的部件。")

        return AgentMessage(
            content="\n".join(lines),
            intent=intent,
            recommendation=recommendation,
        )
