"""根据用户输入生成最小穿搭计划。"""

from __future__ import annotations

import json

from .models import ItemRequest, OutfitRecommendation, Plan, PlanStep
from .tools.wardrobe_query_parser import WardrobeQueryParserTool


ALLOWED_ACTIONS = {"recommend_outfit", "replace_item", "search_items"}
PLAN_FIELDS = {"action", "item_type", "query", "item_requests"}
ITEM_REQUEST_FIELDS = {"item_type", "query"}


class WardrobePlanner:
    """将用户输入规划为整套推荐、部件替换或搜索。"""

    def __init__(self, query_parser: WardrobeQueryParserTool | None = None) -> None:
        self.query_parser = query_parser or WardrobeQueryParserTool()

    def create_plan(
        self,
        user_text: str,
        current_outfit: OutfitRecommendation,
    ) -> Plan:
        allowed = self.query_parser.load_allowed_values()
        response = self.query_parser.llm_client.generate(
            self._build_system_prompt(allowed),
            self._build_user_prompt(user_text, current_outfit),
        )
        return self._parse_response(response, allowed)

    @staticmethod
    def _build_system_prompt(allowed: dict[str, list[str]]) -> str:
        query_instructions = WardrobeQueryParserTool.build_query_instructions(allowed)
        return f"""你是换装 Agent 的 Planner，只负责把用户要求转换为 JSON。
必须只输出一个 JSON 对象，不要解释，不要使用 Markdown。
JSON 必须且只能包含 action、item_type、query、item_requests 四个键。
action 只能是 recommend_outfit、replace_item 或 search_items。
推荐一整套时使用 recommend_outfit，item_type 必须是 null。用户对某个部件提出独立要求时，将它写入 item_requests。
替换当前搭配中的一个部件时使用 replace_item，item_type 必须填写部件英文类别。
搜索、查找或询问服装时使用 search_items；按类别搜索时 item_type 必须填写部件英文类别，按确切名称搜索且类别未知时可以为 null。
item_type 只能从这里选择：{json.dumps(allowed['item_type'], ensure_ascii=False)}
query 必须符合以下规则：
{query_instructions}
item_requests 必须是数组，非 recommend_outfit 动作必须为空数组。
item_requests 中每项必须且只能包含 item_type 和 query；item_type 是部件英文类别，只有 query 指定确切名称时才能为 null。
整套的共同要求写入最外层 query。每个部件的 query 也必须包含上述六个查询键，并同时包含共同要求和该部件的独立要求。
例如“国风搭配，上衣要桃红色，下衣要柳绿色”应使用 recommend_outfit；tops 的 primary_color 填红色、semantic_query 填“国风桃红色”、keywords 填["国风", "桃红色"]；bottoms 的 primary_color 填绿色、semantic_query 填“国风柳绿色”、keywords 填["国风", "柳绿色"]。"""

    @staticmethod
    def _build_user_prompt(
        user_text: str,
        current_outfit: OutfitRecommendation,
    ) -> str:
        outfit_text = "、".join(
            f"{item.type}={item.name}" for item in current_outfit.items
        )
        return f"当前搭配：{outfit_text}\n用户输入：{user_text}"

    def _parse_response(
        self,
        llm_response: str,
        allowed: dict[str, list[str]],
    ) -> Plan:
        try:
            data = json.loads(llm_response)
        except json.JSONDecodeError as error:
            raise ValueError("LLM 没有返回合法 Plan JSON") from error

        if not isinstance(data, dict) or set(data) != PLAN_FIELDS:
            raise ValueError("Plan 必须且只能包含四个规定字段")

        action = data["action"]
        item_type = data["item_type"]
        if action not in ALLOWED_ACTIONS:
            raise ValueError(f"不支持的动作：{action}")
        if action == "recommend_outfit" and item_type is not None:
            raise ValueError("推荐整套搭配时 item_type 必须是 null")
        if action == "replace_item" and item_type not in allowed["item_type"]:
            raise ValueError(f"不支持的部件类别：{item_type}")

        query = self.query_parser.parse_data(data["query"], allowed)
        item_requests = self._parse_item_requests(data["item_requests"], allowed)
        if action != "recommend_outfit" and item_requests:
            raise ValueError("只有推荐整套搭配时可以指定 item_requests")
        if action == "search_items" and item_type is None and query.item_name is None:
            raise ValueError("搜索服装时必须指定部件类别或确切名称")
        if action == "search_items" and item_type is not None and item_type not in allowed[
            "item_type"
        ]:
            raise ValueError(f"不支持的部件类别：{item_type}")
        return Plan(steps=(PlanStep(action, item_type, query, item_requests),))

    def _parse_item_requests(
        self,
        data: object,
        allowed: dict[str, list[str]],
    ) -> tuple[ItemRequest, ...]:
        if not isinstance(data, list):
            raise ValueError("item_requests 必须是数组")

        requests: list[ItemRequest] = []
        item_types: set[str] = set()
        for item in data:
            if not isinstance(item, dict) or set(item) != ITEM_REQUEST_FIELDS:
                raise ValueError("item_requests 中每项必须包含 item_type 和 query")
            request_query = self.query_parser.parse_data(item["query"], allowed)
            request_type = item["item_type"]
            if request_type is None and request_query.item_name is None:
                raise ValueError("未指定部件类别时必须提供确切名称")
            if request_type is not None and request_type not in allowed["item_type"]:
                raise ValueError(f"不支持的部件类别：{request_type}")
            if request_type in item_types:
                raise ValueError(f"重复指定了{request_type}部件")
            if request_type is not None:
                item_types.add(request_type)
            requests.append(ItemRequest(request_type, request_query))

        if "dresses" in item_types and {"tops", "bottoms"} & item_types:
            raise ValueError("不能同时指定连衣裙和上衣或下装")
        return tuple(requests)
