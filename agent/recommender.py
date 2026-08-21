"""最小版部件筛选器。

Intent 目前只有四个可选条件：

1. 主属性（例如“甜美”）
2. 星级（3、4、5，None 表示三种都可以）
3. 主色（例如“红色”）
4. 风格标签（只能是 labels 表中的标签，例如“绮想”）

``recommend_outfits`` 目前只过滤并返回满足条件的部件，不进行套装组合和评分。
"""

from __future__ import annotations

import random
import sqlite3
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any


PROJECT_DIR = Path(__file__).resolve().parent.parent
DATABASE_PATH = PROJECT_DIR / "data" / "database" / "dressup.db"
ALLOWED_QUALITIES = (3, 4, 5)


@dataclass(frozen=True)
class Intent:
    """部件筛选条件；None 表示用户没有指定该项。"""

    main_style: str | None = None
    quality: int | None = None
    primary_color: str | None = None
    style_label: str | None = None


def recommend_outfits(
    intent: Intent,
    database_path: str | Path = DATABASE_PATH,
) -> list[dict[str, Any]]:
    """返回满足 Intent 四项条件的全部部件。

    所有已指定条件之间使用 AND：部件必须同时满足。星级未指定时仍只返回
    3、4、5 星部件，不返回数据库中的 2 星部件。
    """
    if not isinstance(intent, Intent):
        raise TypeError("intent 必须是 Intent 对象")

    database_path = Path(database_path).resolve()
    if not database_path.is_file():
        raise FileNotFoundError(f"找不到数据库：{database_path}")

    connection = sqlite3.connect(database_path)
    connection.row_factory = sqlite3.Row
    try:
        _validate_intent(connection, intent)

        conditions = ["i.quality IN (3, 4, 5)"]
        parameters: list[Any] = []

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


def recommend_complete_outfit(
    intent: Intent,
    database_path: str | Path = DATABASE_PATH,
    random_source: random.Random | None = None,
) -> dict[str, Any]:
    """从 ``recommend_outfits`` 的结果中随机组成一套搭配。

    完整搭配必须包含发型、鞋子，以及“上衣＋下装”或“连衣裙”。程序先随机
    选择一种主体结构进行尝试；如果凑不齐，再尝试另一种。两种都失败才认为
    主体服装不完整。每个部件类型最多选择一个，其他类型有候选就随机选一个。

    如果核心部件不足，返回 ``complete=False`` 和缺失说明，但 ``items`` 仍
    包含当前条件下能够选择的部件。
    """
    candidates = recommend_outfits(intent, database_path)
    chooser = random_source or random.SystemRandom()

    by_type: dict[str, list[dict[str, Any]]] = {}
    for item in candidates:
        by_type.setdefault(item["type"], []).append(item)

    selected: list[dict[str, Any]] = []

    # 发型和鞋子是固定的核心部位；缺少时不阻止后续已有部件的选择。
    for item_type in ("hair", "shoes"):
        if by_type.get(item_type):
            selected.append(chooser.choice(by_type[item_type]))

    has_separates = bool(by_type.get("tops")) and bool(by_type.get("bottoms"))
    has_dress = bool(by_type.get("dresses"))

    first_structure = chooser.choice(("separates", "dress"))
    second_structure = "dress" if first_structure == "separates" else "separates"
    garment_structure: str | None = None

    for structure in (first_structure, second_structure):
        if structure == "separates" and has_separates:
            garment_structure = "separates"
            selected.append(chooser.choice(by_type["tops"]))
            selected.append(chooser.choice(by_type["bottoms"]))
            break
        if structure == "dress" and has_dress:
            garment_structure = "dress"
            selected.append(chooser.choice(by_type["dresses"]))
            break

    if garment_structure is None:
        # 无法形成主体服装时，仍保留已有的上衣或下装供调用方展示。
        if by_type.get("tops"):
            selected.append(chooser.choice(by_type["tops"]))
        if by_type.get("bottoms"):
            selected.append(chooser.choice(by_type["bottoms"]))

    core_types = {"hair", "shoes", "tops", "bottoms", "dresses"}
    for item_type in sorted(set(by_type) - core_types):
        selected.append(chooser.choice(by_type[item_type]))

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
    return {
        "complete": not missing,
        "missing": missing,
        "garment_structure": garment_structure,
        "candidate_count": len(candidates),
        "items": selected,
    }


def _validate_intent(connection: sqlite3.Connection, intent: Intent) -> None:
    """尽早指出拼错或数据库中不存在的 Intent 取值。"""
    if intent.quality is not None and intent.quality not in ALLOWED_QUALITIES:
        raise ValueError("quality 只能是 3、4、5 或 None")

    _validate_database_value(
        connection,
        value=intent.main_style,
        query="SELECT 1 FROM items WHERE main_style_zh = ? LIMIT 1",
        field_name="主属性",
    )
    _validate_database_value(
        connection,
        value=intent.primary_color,
        query=(
            "SELECT 1 FROM item_colors "
            "WHERE role = 'primary' AND family = ? LIMIT 1"
        ),
        field_name="主色",
    )
    _validate_database_value(
        connection,
        value=intent.style_label,
        query="SELECT 1 FROM labels WHERE name = ? LIMIT 1",
        field_name="风格标签",
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


def _row_to_item(row: sqlite3.Row) -> dict[str, Any]:
    labels_text = row["style_labels"] or ""
    return {
        "id": int(row["id"]),
        "name": row["name"],
        "quality": int(row["quality"]),
        "type": row["type"],
        "type_zh": row["type_zh"],
        "main_style": row["main_style"],
        "main_style_zh": row["main_style_zh"],
        "primary_color": row["primary_color"],
        "primary_color_hex": row["primary_color_hex"],
        "style_labels": labels_text.split("|") if labels_text else [],
        "image_path": row["image_path"],
    }


def _outfit_item_sort_key(item: dict[str, Any]) -> tuple[int, str]:
    """让核心服装优先显示，其他类型按内部名称稳定排序。"""
    order = {
        "hair": 0,
        "dresses": 1,
        "tops": 1,
        "bottoms": 2,
        "outerwear": 3,
        "socks": 4,
        "shoes": 5,
    }
    return order.get(item["type"], 10), item["type"]


def main() -> int:
    """示例：随机组成一套“三星、红色主色、甜美主属性”搭配。"""
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")

    intent = Intent(
        quality=3,
        primary_color="红色",
        main_style="典雅",
        style_label=None,
    )
    result = recommend_complete_outfit(intent)

    quality_text = f"{intent.quality}星" if intent.quality is not None else "3～5星均可"
    print(
        "筛选条件："
        f"星级={quality_text}，"
        f"主色={intent.primary_color or '不限'}，"
        f"主属性={intent.main_style or '不限'}，"
        f"风格标签={intent.style_label or '不限'}"
    )
    print(f"候选部件数量：{result['candidate_count']}")
    if result["complete"]:
        structure = (
            "连衣裙"
            if result["garment_structure"] == "dress"
            else "上衣＋下装"
        )
        print(f"成功组成一套搭配，主体结构：{structure}")
    else:
        print("无法凑成一套完整搭配")
        print("缺少：" + "、".join(result["missing"]))

    print("已选部件：")
    for item in result["items"]:
        labels = "、".join(item["style_labels"]) or "无"
        print(
            f"{item['id']} | {item['name']} | {item['type_zh']} | "
            f"{item['quality']}星 | {item['main_style_zh']} | "
            f"{item['primary_color']} | 标签：{labels}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
