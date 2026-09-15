"""根据结构化 WardrobeQuery 生成完整穿搭的推荐工具。"""

from __future__ import annotations

import logging
import random
import sqlite3
from pathlib import Path

from ..models import ItemRequest, OutfitItem, OutfitRecommendation, WardrobeQuery
from ..query_expander import QueryExpander, QueryExpansion
from .semantic_search import SemanticSearch


PROJECT_DIR = Path(__file__).resolve().parents[2]
DATABASE_PATH = PROJECT_DIR / "data" / "database" / "dressup.db"
DEFAULT_OUTFIT_ID = 10043
ALLOWED_QUALITIES = (3, 4, 5)
MIN_DIRECT_MATCHES = 10
RRF_K = 60
REQUIRED_ITEM_TYPES = {"hair", "shoes"}
GARMENT_ITEM_TYPES = {"tops", "bottoms", "dresses"}
CORE_ITEM_TYPES = REQUIRED_ITEM_TYPES | GARMENT_ITEM_TYPES
OPTIONAL_ITEM_PROBABILITY = 0.5
LOGGER = logging.getLogger(__name__)


class OutfitRecommendationTool:
    """查询候选部件并随机组成一套完整搭配。"""

    name = "recommend_outfit"

    def __init__(
        self,
        database_path: str | Path = DATABASE_PATH,
        random_source: random.Random | None = None,
        query_expander: QueryExpander | None = None,
    ) -> None:
        self.database_path = Path(database_path)
        self.random_source = random_source or random.SystemRandom()
        self.semantic_search: SemanticSearch | None = None
        self.query_expander = query_expander or QueryExpander()
        self.query_expansions: list[QueryExpansion] = []

    def clear_query_expansions(self) -> None:
        self.query_expansions.clear()

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

        candidates = self.query_items(
            query,
            included_item_types=self._choose_item_types_for_outfit(),
        )
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

        for item_type in sorted(set(by_type) - CORE_ITEM_TYPES):
            add_item(item_type)

        return _build_recommendation(
            selected,
            candidate_count=len(candidates),
            garment_structure=garment_structure,
        )

    def _choose_item_types_for_outfit(self) -> tuple[str, ...]:
        connection = sqlite3.connect(self.database_path)
        try:
            item_types = {
                row[0]
                for row in connection.execute(
                    "SELECT DISTINCT type FROM items WHERE quality IN (3, 4, 5)"
                )
            }
        finally:
            connection.close()

        included_item_types = set(CORE_ITEM_TYPES)
        for item_type in sorted(item_types - CORE_ITEM_TYPES):
            if self.random_source.random() < OPTIONAL_ITEM_PROBABILITY:
                included_item_types.add(item_type)
        return tuple(sorted(included_item_types))

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
        if query.semantic_query is not None:
            return candidates[0]
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
        included_item_types: tuple[str, ...] = (),
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
            if included_item_types:
                placeholders = ", ".join("?" for _ in included_item_types)
                conditions.append(f"i.type IN ({placeholders})")
                parameters.extend(included_item_types)
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
                candidate_ids = [int(row["id"]) for row in rows]
                rows_by_id = {int(row["id"]): row for row in rows}
                original_semantic_ids = self._semantic_search(
                    query.semantic_query,
                    candidate_ids,
                )
                original_keyword_rows = _query_keyword_rows(
                    connection,
                    base_sql,
                    parameters,
                    query.keywords,
                )
                original_keyword_ids = _rank_keyword_rows(
                    original_keyword_rows,
                    query.keywords,
                )
                initial_ids = tuple(
                    dict.fromkeys((*original_semantic_ids, *original_keyword_ids))
                )
                hard_filter_can_satisfy = (
                    bool(rows)
                    if item_type is not None
                    else _can_form_minimum_outfit(rows)
                )
                initial_result_is_complete = (
                    bool(initial_ids)
                    if item_type is not None
                    else _can_form_minimum_outfit(
                        [rows_by_id[item_id] for item_id in initial_ids]
                    )
                )

                ranked_lists: list[list[int]] = [
                    original_semantic_ids,
                    original_keyword_ids,
                ]
                weights = [1.0, 0.8]
                if _should_expand_query(
                    query,
                    hard_filter_can_satisfy,
                    initial_result_is_complete,
                    len(original_keyword_ids),
                ):
                    try:
                        expansion = self.query_expander.expand(query)
                    except (RuntimeError, ValueError) as error:
                        LOGGER.warning("查询扩展失败，使用原始查询：%s", error)
                    else:
                        if expansion not in self.query_expansions:
                            self.query_expansions.append(expansion)
                        detail_ids = self._semantic_search(
                            expansion.detail_query,
                            candidate_ids,
                        )
                        detail_keyword_ids = _rank_keyword_rows(
                            _query_keyword_rows(
                                connection,
                                base_sql,
                                parameters,
                                expansion.detail_keywords,
                            ),
                            expansion.detail_keywords,
                        )
                        ranked_lists = [
                            original_semantic_ids,
                            original_keyword_ids,
                            detail_ids,
                            detail_keyword_ids,
                        ]
                        weights = [1.0, 0.8, 0.8, 0.8]

                ranked_ids = _rrf_fuse(ranked_lists, weights)
                rows = [rows_by_id[item_id] for item_id in ranked_ids]
            return [_row_to_item(row) for row in rows]
        finally:
            connection.close()

    def _semantic_search(self, text: str, candidate_ids: list[int]) -> list[int]:
        if self.semantic_search is None:
            self.semantic_search = SemanticSearch()
        return self.semantic_search.search(text, candidate_ids)


def _should_expand_query(
    query: WardrobeQuery,
    hard_filter_can_satisfy: bool,
    initial_result_is_complete: bool,
    direct_match_count: int,
) -> bool:
    if query.semantic_query is None or query.item_name is not None:
        return False
    if not hard_filter_can_satisfy:
        return False
    return (
        not initial_result_is_complete
        or direct_match_count < MIN_DIRECT_MATCHES
    )


def _can_form_minimum_outfit(rows: list[sqlite3.Row]) -> bool:
    item_types = {row["type"] for row in rows}
    has_hair = "hair" in item_types
    has_shoes = "shoes" in item_types
    has_dress = "dresses" in item_types
    has_separates = {"tops", "bottoms"} <= item_types
    return has_hair and has_shoes and (has_dress or has_separates)


def _query_keyword_rows(
    connection: sqlite3.Connection,
    base_sql: str,
    parameters: list[object],
    keywords: tuple[str, ...],
) -> list[sqlite3.Row]:
    conditions = ["i.summary_zh LIKE ?" for _ in keywords]
    if not conditions:
        return []
    return connection.execute(
        f"{base_sql} AND ({' OR '.join(conditions)}) ORDER BY i.id",
        [*parameters, *(f"%{keyword}%" for keyword in keywords)],
    ).fetchall()


def _rank_keyword_rows(
    rows: list[sqlite3.Row],
    keywords: tuple[str, ...],
) -> list[int]:
    return [
        int(row["id"])
        for row in sorted(
            rows,
            key=lambda row: (
                -sum(keyword in (row["summary_zh"] or "") for keyword in keywords),
                int(row["id"]),
            ),
        )
    ]


def _rrf_fuse(
    ranked_lists: list[list[int]],
    weights: list[float],
    rrf_k: int = RRF_K,
) -> list[int]:
    scores: dict[int, float] = {}
    for results, weight in zip(ranked_lists, weights, strict=True):
        for rank, item_id in enumerate(results, start=1):
            scores[item_id] = scores.get(item_id, 0.0) + weight / (rrf_k + rank)
    return sorted(scores, key=lambda item_id: (-scores[item_id], item_id))


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
