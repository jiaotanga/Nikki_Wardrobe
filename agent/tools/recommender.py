"""根据结构化 Intent 生成完整穿搭的推荐工具。"""

from __future__ import annotations

import random
import sqlite3
from pathlib import Path

from ..models import Intent, OutfitItem, OutfitRecommendation


PROJECT_DIR = Path(__file__).resolve().parents[2]
DATABASE_PATH = PROJECT_DIR / "data" / "database" / "dressup.db"
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

    def run(self, intent: Intent) -> OutfitRecommendation:
        candidates = self._query_candidates(intent)
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

        missing: list[str] = []
        if not by_type.get("hair"):
            missing.append("发型")
        if not by_type.get("shoes"):
            missing.append("鞋子")
        if garment_structure is None:
            if not by_type.get("tops") and not by_type.get("bottoms"):
                missing.append("上衣＋下装或连衣裙")
            elif not by_type.get("tops"):
                missing.append("上衣或连衣裙")
            else:
                missing.append("下装或连衣裙")

        selected.sort(key=_outfit_item_sort_key)
        return OutfitRecommendation(
            complete=not missing,
            missing=tuple(missing),
            garment_structure=garment_structure,
            candidate_count=len(candidates),
            items=tuple(selected),
        )

    def _query_candidates(self, intent: Intent) -> list[OutfitItem]:
        if not isinstance(intent, Intent):
            raise TypeError("intent 必须是 Intent 对象")
        if not self.database_path.is_file():
            raise FileNotFoundError(f"找不到数据库：{self.database_path}")

        connection = sqlite3.connect(self.database_path)
        connection.row_factory = sqlite3.Row
        try:
            _validate_intent(connection, intent)
            conditions = ["i.quality IN (3, 4, 5)"]
            parameters: list[object] = []

            if intent.main_style is not None:
                conditions.append("i.main_style_zh = ?")
                parameters.append(intent.main_style)
            if intent.quality is not None:
                conditions.append("i.quality = ?")
                parameters.append(intent.quality)
            if intent.primary_color is not None:
                conditions.append("primary_color.family = ?")
                parameters.append(intent.primary_color)
            if intent.style_label is not None:
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
                parameters.append(intent.style_label)

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


def _validate_intent(connection: sqlite3.Connection, intent: Intent) -> None:
    if intent.quality is not None and intent.quality not in ALLOWED_QUALITIES:
        raise ValueError("quality 只能是 3、4、5 或 None")

    _validate_database_value(
        connection,
        intent.main_style,
        "SELECT 1 FROM items WHERE main_style_zh = ? LIMIT 1",
        "主属性",
    )
    _validate_database_value(
        connection,
        intent.primary_color,
        "SELECT 1 FROM item_colors WHERE role = 'primary' AND family = ? LIMIT 1",
        "主色",
    )
    _validate_database_value(
        connection,
        intent.style_label,
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
