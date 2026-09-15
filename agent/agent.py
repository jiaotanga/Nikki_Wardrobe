"""换装推荐 Agent。"""

from __future__ import annotations

from .message import AgentMessage, MessageProcessor, UserMessage
from .models import ItemRequest, OutfitRecommendation, WardrobeQuery
from .planner import WardrobePlanner
from .tools import (
    ItemSearchTool,
    OutfitItemReplacementTool,
    OutfitRecommendationTool,
    ToolRegistry,
    WardrobeQueryParserTool,
)


class WardrobeAgent:
    """维护当前搭配并执行 Planner 生成的操作。"""

    def __init__(
        self,
        query_parser: WardrobeQueryParserTool | None = None,
        planner: WardrobePlanner | None = None,
        recommender: OutfitRecommendationTool | None = None,
        replacement_tool: OutfitItemReplacementTool | None = None,
        search_tool: ItemSearchTool | None = None,
        message_processor: MessageProcessor | None = None,
        initial_outfit: OutfitRecommendation | None = None,
    ) -> None:
        self.message_processor = message_processor or MessageProcessor()
        query_parser = query_parser or WardrobeQueryParserTool()
        recommender = recommender or OutfitRecommendationTool()
        self.recommender = recommender
        self.planner = planner or WardrobePlanner(query_parser)
        replacement_tool = replacement_tool or OutfitItemReplacementTool(
            recommender.recommend_item
        )
        search_tool = search_tool or ItemSearchTool(recommender.query_items)
        self.tools = ToolRegistry()
        self.tools.register(recommender.name, recommender.run)
        self.tools.register("recommend_item", recommender.recommend_item)
        self.tools.register(replacement_tool.name, replacement_tool.run)
        self.tools.register(search_tool.name, search_tool.run)

        self.current_query = WardrobeQuery()
        self.current_outfit = (
            initial_outfit
            or recommender.load_outfit()
            or recommender.run(self.current_query)
        )

    def handle(self, message: UserMessage) -> AgentMessage:
        self.recommender.clear_query_expansions()
        user_text = self.message_processor.normalize(message)
        plan = self.planner.create_plan(user_text, self.current_outfit)
        query = self.current_query
        outfit = self.current_outfit
        item_requests = ()

        for step in plan.steps:
            if step.action == "recommend_outfit":
                query = step.query
                item_requests = step.item_requests
                outfit = self.tools.call(
                    "recommend_outfit",
                    query,
                    step.item_requests,
                )
            elif step.action == "replace_item":
                if step.item_type is None:
                    raise ValueError("替换部件时必须指定部件类别")
                item_requests = (ItemRequest(step.item_type, step.query),)
                query = _merge_query(query, step.query)
                outfit = self.tools.call(
                    "replace_item",
                    outfit,
                    step.item_type,
                    query,
                )
            elif step.action == "search_items":
                items = self.tools.call("search_items", step.query, step.item_type)
                return self.message_processor.build_item_list_reply(
                    step.query,
                    items,
                    tuple(self.recommender.query_expansions),
                )

        self.current_query = query
        self.current_outfit = outfit
        return self.message_processor.build_outfit_reply(
            query,
            outfit,
            item_requests,
            tuple(self.recommender.query_expansions),
        )


def _merge_query(current: WardrobeQuery, update: WardrobeQuery) -> WardrobeQuery:
    return WardrobeQuery(
        main_style=update.main_style or current.main_style,
        quality=update.quality or current.quality,
        primary_color=update.primary_color or current.primary_color,
        item_name=update.item_name or current.item_name,
        semantic_query=update.semantic_query or current.semantic_query,
        keywords=update.keywords or current.keywords,
    )
