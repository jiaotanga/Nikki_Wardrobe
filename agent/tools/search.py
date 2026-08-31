"""搜索指定类别的服装部件。"""

from __future__ import annotations

from collections.abc import Callable

from ..models import Intent, OutfitItem


SEARCH_RESULT_LIMIT = 12


class ItemSearchTool:
    """复用候选查询并返回服装列表。"""

    name = "search_items"

    def __init__(
        self,
        query_items: Callable[..., list[OutfitItem]],
    ) -> None:
        self.query_items = query_items

    def run(self, intent: Intent, item_type: str) -> tuple[OutfitItem, ...]:
        items = self.query_items(intent, item_type=item_type)
        return tuple(items[:SEARCH_RESULT_LIMIT])
