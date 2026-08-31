"""根据用户输入生成最小穿搭计划。"""

from __future__ import annotations

import json

from .models import OutfitRecommendation, Plan, PlanStep
from .tools.intent_parser import IntentParserTool


ALLOWED_ACTIONS = {"recommend_outfit", "replace_item", "search_items"}
PLAN_FIELDS = {"action", "item_type", "intent"}


class WardrobePlanner:
    """将用户输入规划为整套推荐、部件替换或搜索。"""

    def __init__(self, intent_parser: IntentParserTool | None = None) -> None:
        self.intent_parser = intent_parser or IntentParserTool()

    def create_plan(
        self,
        user_text: str,
        current_outfit: OutfitRecommendation,
    ) -> Plan:
        allowed = self.intent_parser.load_allowed_values()
        response = self.intent_parser.llm_client.generate(
            self._build_system_prompt(allowed),
            self._build_user_prompt(user_text, current_outfit),
        )
        return self._parse_response(response, allowed)

    @staticmethod
    def _build_system_prompt(allowed: dict[str, list[str]]) -> str:
        return f"""你是换装 Agent 的 Planner，只负责把用户要求转换为 JSON。
必须只输出一个 JSON 对象，不要解释，不要使用 Markdown。
JSON 必须且只能包含 action、item_type、intent 三个键。
action 只能是 recommend_outfit、replace_item 或 search_items。
推荐一整套时使用 recommend_outfit，item_type 必须是 null。
替换当前搭配中的一个部件时使用 replace_item，item_type 必须填写部件英文类别。
搜索、查找或询问某类服装有哪些时使用 search_items，item_type 必须填写部件英文类别。
item_type 只能从这里选择：{json.dumps(allowed['item_type'], ensure_ascii=False)}
intent 必须且只能包含 main_style、quality、primary_color、style_label 四个键。
用户本轮没有指定的 intent 值必须是 null。
quality 只能是整数 3、4、5；只有用户明确提到星级时才填写。
primary_color 只有用户明确提到颜色时才填写。
main_style 和 style_label 可以根据相近语义选择；没有合适值就填 null。
main_style 只能从这里选择：{json.dumps(allowed['main_style'], ensure_ascii=False)}
primary_color 只能从这里选择：{json.dumps(allowed['primary_color'], ensure_ascii=False)}
style_label 只能从这里选择：{json.dumps(allowed['style_label'], ensure_ascii=False)}"""

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
            raise ValueError("Plan 必须且只能包含三个规定字段")

        action = data["action"]
        item_type = data["item_type"]
        if action not in ALLOWED_ACTIONS:
            raise ValueError(f"不支持的动作：{action}")
        if action == "recommend_outfit" and item_type is not None:
            raise ValueError("推荐整套搭配时 item_type 必须是 null")
        if action in {"replace_item", "search_items"} and item_type not in allowed[
            "item_type"
        ]:
            raise ValueError(f"不支持的部件类别：{item_type}")

        intent = self.intent_parser.parse_data(data["intent"], allowed)
        return Plan(steps=(PlanStep(action, item_type, intent),))
