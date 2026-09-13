"""根据结构化 WardrobeQuery 生成完整穿搭的推荐工具。"""

from __future__ import annotations

import random
import sqlite3
from pathlib import Path

from ..models import ItemRequest, OutfitItem, OutfitRecommendation, WardrobeQuery
from .semantic_search import SemanticSearch


PROJECT_DIR = Path(__file__).resolve().parents[2]
DATABASE_PATH = PROJECT_DIR / "data" / "database" / "dressup.db"
DEFAULT_OUTFIT_ID = 10043
ALLOWED_QUALITIES = (3, 4, 5)


class OutfitRecommendationTool:
    """查询候选部件并随机组成一套完整搭配。"""

    name = "recommend_outfit"

    def __init__(
        self,
        database_path: str | Path = DATABASE_PATH,
        random_source: random.Random | None = None,
    ) -> None:
        self.database_path = Path(database_path)
        self.random_source = random_source or random.SystemRandom()
        self.semantic_search: SemanticSearch | None = None

    def run(
        self,
        query: WardrobeQuery,
        item_requests: tuple[ItemRequest, ...] = (),
    ) -> OutfitRecommendation:
        selected: list[OutfitItem] = []
        selected_types: set[str] = set()
        for request in item_requests:
            item = self.recommend_item(request.query, request.item_type)
            if item.type in selected_types:
                raise ValueError(f"重复指定了{item.type}部件")
            selected.append(item)
            selected_types.add(item.type)

        if "dresses" in selected_types and {"tops", "bottoms"} & selected_types:
            raise ValueError("不能同时指定连衣裙和上衣或下装")

        candidates = self.query_items(query)
        by_type: dict[str, list[OutfitItem]] = {}
        for item in candidates:
            by_type.setdefault(item.type, []).append(item)

        def add_item(item_type: str) -> None:
            if item_type in selected_types or not by_type.get(item_type):
                return
            selected.append(
                self.recommend_item(
                    query,
                    item_type,
                    candidate_items=by_type[item_type],
                )
            )
            selected_types.add(item_type)

        for item_type in ("hair", "shoes"):
            add_item(item_type)

        available_types = set(by_type) | selected_types
        has_separates = {"tops", "bottoms"} <= available_types
        has_dress = "dresses" in available_types
        if "dresses" in selected_types:
            structures = ("dress",)
        elif {"tops", "bottoms"} & selected_types:
            structures = ("separates",)
        else:
            first_structure = self.random_source.choice(("separates", "dress"))
            second_structure = (
                "dress" if first_structure == "separates" else "separates"
            )
            structures = (first_structure, second_structure)
        garment_structure: str | None = None

        for structure in structures:
            if structure == "separates" and has_separates:
                garment_structure = "separates"
                add_item("tops")
                add_item("bottoms")
                break
            if structure == "dress" and has_dress:
                garment_structure = "dress"
                add_item("dresses")
                break

        if garment_structure is None:
            for item_type in ("tops", "bottoms"):
                add_item(item_type)

        core_types = {"hair", "shoes", "tops", "bottoms", "dresses"}
        for item_type in sorted(set(by_type) - core_types):
            add_item(item_type)

        return _build_recommendation(
            selected,
            candidate_count=len(candidates),
            garment_structure=garment_structure,
        )

    def recommend_item(
        self,
        query: WardrobeQuery,
        item_type: str | None = None,
        excluded_item_ids: tuple[int, ...] = (),
        candidate_items: list[OutfitItem] | None = None,
    ) -> OutfitItem:
        """推荐指定类别的一件部件。"""

        if item_type is None and query.item_name is None:
            raise ValueError("未指定类别时必须提供确切部件名称")

        if candidate_items is None:
            candidates = self.query_items(
                query,
                item_type=item_type,
                excluded_item_ids=excluded_item_ids,
            )
        else:
            candidates = [
                item
                for item in candidate_items
                if item.type == item_type and item.id not in excluded_item_ids
            ]
        if not candidates:
            raise ValueError(f"没有找到符合条件的{item_type or query.item_name}部件")
        return self.random_source.choice(candidates)

    def load_outfit(
        self,
        outfit_id: int = DEFAULT_OUTFIT_ID,
    ) -> OutfitRecommendation | None:
        """按照套装 ID 读取一套已有搭配。"""

        connection = sqlite3.connect(self.database_path)
        try:
            item_ids = tuple(
                row[0]
                for row in connection.execute(
                    "SELECT item_id FROM outfit_items WHERE outfit_id = ?",
                    (outfit_id,),
                )
            )
        finally:
            connection.close()

        if not item_ids:
            return None
        items = self.query_items(WardrobeQuery(), item_ids=item_ids)
        return _build_recommendation(items, candidate_count=len(items))

    def query_items(
        self,
        query: WardrobeQuery,
        item_type: str | None = None,
        item_ids: tuple[int, ...] = (),
        excluded_item_ids: tuple[int, ...] = (),
    ) -> list[OutfitItem]:
        if not isinstance(query, WardrobeQuery):
            raise TypeError("query 必须是 WardrobeQuery 对象")
        if not self.database_path.is_file():
            raise FileNotFoundError(f"找不到数据库：{self.database_path}")

        connection = sqlite3.connect(self.database_path)
        connection.row_factory = sqlite3.Row
        try:
            _validate_query(connection, query)
            conditions = ["i.quality IN (3, 4, 5)"]
            parameters: list[object] = []

            if query.main_style is not None:
                conditions.append("i.main_style_zh = ?")
                parameters.append(query.main_style)
            if query.quality is not None:
                conditions.append("i.quality = ?")
                parameters.append(query.quality)
            if query.primary_color is not None:
                conditions.append("primary_color.family = ?")
                parameters.append(query.primary_color)
            if query.item_name is not None:
                conditions.append("i.name = ?")
                parameters.append(query.item_name)
            if item_type is not None:
                conditions.append("i.type = ?")
                parameters.append(item_type)
            if item_ids:
                placeholders = ", ".join("?" for _ in item_ids)
                conditions.append(f"i.id IN ({placeholders})")
                parameters.extend(item_ids)
            if excluded_item_ids:
                placeholders = ", ".join("?" for _ in excluded_item_ids)
                conditions.append(f"i.id NOT IN ({placeholders})")
                parameters.extend(excluded_item_ids)

            base_sql = f"""
                SELECT
                    i.id,
                    i.name,
                    i.quality,
                    i.type,
                    i.type_zh,
                    i.main_style,
                    i.main_style_zh,
                    i.summary_zh,
                    primary_color.family AS primary_color,
                    primary_color.hex AS primary_color_hex,
                    i.image_path,
                    (
                        SELECT GROUP_CONCAT(label_name, '|')
                        FROM (
                            SELECT l.name AS label_name
                            FROM item_labels AS il
                            JOIN labels AS l ON l.id = il.label_id
                            WHERE il.item_id = i.id
                            ORDER BY l.id
                        )
                    ) AS style_labels
                FROM items AS i
                JOIN item_colors AS primary_color
                  ON primary_color.item_id = i.id
                 AND primary_color.role = 'primary'
                WHERE {' AND '.join(conditions)}
            """
            rows = connection.execute(
                f"{base_sql} ORDER BY i.id",
                parameters,
            ).fetchall()
            if query.semantic_query:
                keyword_conditions = [
                    "i.summary_zh LIKE ?" for _ in query.keywords
                ]
                keyword_rows = (
                    connection.execute(
                        f"{base_sql} AND ({' OR '.join(keyword_conditions)}) "
                        "ORDER BY i.id",
                        [
                            *parameters,
                            *(f"%{keyword}%" for keyword in query.keywords),
                        ],
                    ).fetchall()
                    if keyword_conditions
                    else []
                )
                if self.semantic_search is None:
                    self.semantic_search = SemanticSearch()
                semantic_ids = self.semantic_search.search(
                    query.semantic_query,
                    [int(row["id"]) for row in rows],
                )
                keyword_ids = {int(row["id"]) for row in keyword_rows}
                rows_by_id = {int(row["id"]): row for row in rows}
                rows = keyword_rows + [
                    rows_by_id[item_id]
                    for item_id in semantic_ids
                    if item_id not in keyword_ids
                ]
            return [_row_to_item(row) for row in rows]
        finally:
            connection.close()


def _validate_query(connection: sqlite3.Connection, query: WardrobeQuery) -> None:
    if query.quality is not None and query.quality not in ALLOWED_QUALITIES:
        raise ValueError("quality 只能是 3、4、5 或 None")

    _validate_database_value(
        connection,
        query.main_style,
        "SELECT 1 FROM items WHERE main_style_zh = ? LIMIT 1",
        "主属性",
    )
    _validate_database_value(
        connection,
        query.primary_color,
        "SELECT 1 FROM item_colors WHERE role = 'primary' AND family = ? LIMIT 1",
        "主色",
    )
    _validate_database_value(
        connection,
        query.item_name,
        "SELECT 1 FROM items WHERE name = ? LIMIT 1",
        "部件名称",
    )
def _validate_database_value(
    connection: sqlite3.Connection,
    value: str | None,
    query: str,
    field_name: str,
) -> None:
    if value is None:
        return
    if not value.strip():
        raise ValueError(f"{field_name}不能是空字符串")
    if connection.execute(query, (value,)).fetchone() is None:
        raise ValueError(f"数据库中不存在{field_name}：{value}")


def _row_to_item(row: sqlite3.Row) -> OutfitItem:
    labels_text = row["style_labels"] or ""
    return OutfitItem(
        id=int(row["id"]),
        name=row["name"],
        quality=int(row["quality"]),
        type=row["type"],
        type_zh=row["type_zh"],
        main_style=row["main_style"],
        main_style_zh=row["main_style_zh"],
        primary_color=row["primary_color"],
        primary_color_hex=row["primary_color_hex"],
        style_labels=tuple(labels_text.split("|")) if labels_text else (),
        summary_zh=row["summary_zh"],
        image_path=row["image_path"],
    )


def _build_recommendation(
    items: list[OutfitItem],
    candidate_count: int,
    garment_structure: str | None = None,
) -> OutfitRecommendation:
    item_types = {item.type for item in items}
    if garment_structure is None:
        if "dresses" in item_types:
            garment_structure = "dress"
        elif {"tops", "bottoms"} <= item_types:
            garment_structure = "separates"

    missing: list[str] = []
    if "hair" not in item_types:
        missing.append("发型")
    if "shoes" not in item_types:
        missing.append("鞋子")
    if garment_structure is None:
        if "tops" not in item_types and "bottoms" not in item_types:
            missing.append("上衣＋下装或连衣裙")
        elif "tops" not in item_types:
            missing.append("上衣或连衣裙")
        else:
            missing.append("下装或连衣裙")

    items.sort(key=_outfit_item_sort_key)
    return OutfitRecommendation(
        complete=not missing,
        missing=tuple(missing),
        garment_structure=garment_structure,
        candidate_count=candidate_count,
        items=tuple(items),
    )


def _outfit_item_sort_key(item: OutfitItem) -> tuple[int, str]:
    order = {
        "hair": 0,
        "dresses": 1,
        "tops": 1,
        "bottoms": 2,
        "outerwear": 3,
        "socks": 4,
        "shoes": 5,
    }
    return order.get(item.type, 10), item.type
