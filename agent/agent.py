"""换装推荐 Agent。"""

from __future__ import annotations

from .message import AgentMessage, MessageProcessor, UserMessage
from .models import Intent, OutfitRecommendation
from .planner import WardrobePlanner
from .tools import (
    IntentParserTool,
    ItemSearchTool,
    OutfitItemReplacementTool,
    OutfitRecommendationTool,
    ToolRegistry,
)


class WardrobeAgent:
    """维护当前搭配并执行 Planner 生成的操作。"""

    def __init__(
        self,
        intent_parser: IntentParserTool | None = None,
        planner: WardrobePlanner | None = None,
        recommender: OutfitRecommendationTool | None = None,
        replacement_tool: OutfitItemReplacementTool | None = None,
        search_tool: ItemSearchTool | None = None,
        message_processor: MessageProcessor | None = None,
        initial_outfit: OutfitRecommendation | None = None,
    ) -> None:
        self.message_processor = message_processor or MessageProcessor()
        intent_parser = intent_parser or IntentParserTool()
        recommender = recommender or OutfitRecommendationTool()
        self.planner = planner or WardrobePlanner(intent_parser)
        replacement_tool = replacement_tool or OutfitItemReplacementTool(
            recommender.recommend_item
        )
        search_tool = search_tool or ItemSearchTool(recommender.query_items)
        self.tools = ToolRegistry()
        self.tools.register(recommender.name, recommender.run)
        self.tools.register("recommend_item", recommender.recommend_item)
        self.tools.register(replacement_tool.name, replacement_tool.run)
        self.tools.register(search_tool.name, search_tool.run)

        self.current_intent = Intent()
        self.current_outfit = (
            initial_outfit
            or recommender.load_outfit()
            or recommender.run(self.current_intent)
        )

    def handle(self, message: UserMessage) -> AgentMessage:
        user_text = self.message_processor.normalize(message)
        plan = self.planner.create_plan(user_text, self.current_outfit)
        intent = self.current_intent
        outfit = self.current_outfit

        for step in plan.steps:
            if step.action == "recommend_outfit":
                intent = step.intent
                outfit = self.tools.call("recommend_outfit", intent)
            elif step.action == "replace_item":
                if step.item_type is None:
                    raise ValueError("替换部件时必须指定部件类别")
                intent = _merge_intent(intent, step.intent)
                outfit = self.tools.call(
                    "replace_item",
                    outfit,
                    step.item_type,
                    intent,
                )
            elif step.action == "search_items":
                if step.item_type is None:
                    raise ValueError("搜索服装时必须指定部件类别")
                items = self.tools.call("search_items", step.intent, step.item_type)
                return self.message_processor.build_item_list_reply(step.intent, items)

        self.current_intent = intent
        self.current_outfit = outfit
        return self.message_processor.build_outfit_reply(intent, outfit)


def _merge_intent(current: Intent, update: Intent) -> Intent:
    return Intent(
        main_style=update.main_style or current.main_style,
        quality=update.quality or current.quality,
        primary_color=update.primary_color or current.primary_color,
        style_label=update.style_label or current.style_label,
    )
