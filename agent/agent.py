"""换装推荐 Agent。"""

from __future__ import annotations

from .message import AgentMessage, MessageProcessor, UserMessage
from .models import Intent, OutfitRecommendation
from .tools import IntentParserTool, OutfitRecommendationTool, ToolRegistry


class WardrobeAgent:
    """编排意图解析和穿搭推荐两个工具。"""

    def __init__(
        self,
        intent_parser: IntentParserTool | None = None,
        recommender: OutfitRecommendationTool | None = None,
        message_processor: MessageProcessor | None = None,
    ) -> None:
        self.message_processor = message_processor or MessageProcessor()
        intent_parser = intent_parser or IntentParserTool()
        recommender = recommender or OutfitRecommendationTool()
        self.tools = ToolRegistry()
        self.tools.register(intent_parser.name, intent_parser.run)
        self.tools.register(recommender.name, recommender.run)

    def handle(self, message: UserMessage) -> AgentMessage:
        user_text = self.message_processor.normalize(message)
        intent: Intent = self.tools.call("parse_intent", user_text)
        recommendation: OutfitRecommendation = self.tools.call(
            "recommend_outfit",
            intent,
        )
        return self.message_processor.build_reply(intent, recommendation)
