"""替换当前搭配中的单个部件。"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import replace

from ..models import Intent, OutfitItem, OutfitRecommendation


class OutfitItemReplacementTool:
    """推荐同类别新部件并替换当前搭配。"""

    name = "replace_item"

    def __init__(
        self,
        recommend_item: Callable[[Intent, str, tuple[int, ...]], OutfitItem],
    ) -> None:
        self.recommend_item = recommend_item

    def run(
        self,
        current_outfit: OutfitRecommendation,
        item_type: str,
        intent: Intent,
    ) -> OutfitRecommendation:
        current_items = tuple(
            item for item in current_outfit.items if item.type == item_type
        )
        if not current_items:
            raise ValueError(f"当前搭配中没有 {item_type} 部件")

        new_item = self.recommend_item(
            intent,
            item_type,
            tuple(item.id for item in current_items),
        )
        items = tuple(
            new_item if item.type == item_type else item
            for item in current_outfit.items
        )
        return replace(current_outfit, items=items)
