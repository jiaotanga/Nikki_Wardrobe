"""根据结构化 WardrobeQuery 生成完整穿搭的推荐工具。"""

from __future__ import annotations

import random
import sqlite3
from pathlib import Path

from ..models import OutfitItem, OutfitRecommendation, WardrobeQuery


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

    def run(self, query: WardrobeQuery) -> OutfitRecommendation:
        candidates = self.query_items(query)
        by_type: dict[str, list[OutfitItem]] = {}
        for item in candidates:
            by_type.setdefault(item.type, []).append(item)

        selected: list[OutfitItem] = []
        for item_type in ("hair", "shoes"):
            if by_type.get(item_type):
                selected.append(self.random_source.choice(by_type[item_type]))

        has_separates = bool(by_type.get("tops")) and bool(by_type.get("bottoms"))
        has_dress = bool(by_type.get("dresses"))
        first_structure = self.random_source.choice(("separates", "dress"))
        second_structure = "dress" if first_structure == "separates" else "separates"
        garment_structure: str | None = None

        for structure in (first_structure, second_structure):
            if structure == "separates" and has_separates:
                garment_structure = "separates"
                selected.append(self.random_source.choice(by_type["tops"]))
                selected.append(self.random_source.choice(by_type["bottoms"]))
                break
            if structure == "dress" and has_dress:
                garment_structure = "dress"
                selected.append(self.random_source.choice(by_type["dresses"]))
                break

        if garment_structure is None:
            for item_type in ("tops", "bottoms"):
                if by_type.get(item_type):
                    selected.append(self.random_source.choice(by_type[item_type]))

        core_types = {"hair", "shoes", "tops", "bottoms", "dresses"}
        for item_type in sorted(set(by_type) - core_types):
            selected.append(self.random_source.choice(by_type[item_type]))

        return _build_recommendation(
            selected,
            candidate_count=len(candidates),
            garment_structure=garment_structure,
        )

    def recommend_item(
        self,
        query: WardrobeQuery,
        item_type: str,
        excluded_item_ids: tuple[int, ...] = (),
    ) -> OutfitItem:
        """推荐指定类别的一件部件。"""

        candidates = self.query_items(
            query,
            item_type=item_type,
            excluded_item_ids=excluded_item_ids,
        )
        if not candidates:
            raise ValueError(f"没有找到符合条件的{item_type}部件")
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
            if query.style_label is not None:
                conditions.append(
                    """
                    EXISTS (
                        SELECT 1
                        FROM item_labels AS wanted_item_label
                        JOIN labels AS wanted_label
                          ON wanted_label.id = wanted_item_label.label_id
                        WHERE wanted_item_label.item_id = i.id
                          AND wanted_label.name = ?
                    )
                    """
                )
                parameters.append(query.style_label)
            if query.keywords:
                keyword_conditions = [
                    "i.summary_zh LIKE ?" for _ in query.keywords
                ]
                conditions.append(f"({' OR '.join(keyword_conditions)})")
                parameters.extend(f"%{keyword}%" for keyword in query.keywords)

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

            query = f"""
                SELECT
                    i.id,
                    i.name,
                    i.quality,
                    i.type,
                    i.type_zh,
                    i.main_style,
                    i.main_style_zh,
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
                ORDER BY i.id
            """
            rows = connection.execute(query, parameters).fetchall()
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
        query.style_label,
        "SELECT 1 FROM labels WHERE name = ? LIMIT 1",
        "风格标签",
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
