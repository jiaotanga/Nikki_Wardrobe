"""从部件 JSON 和图片全量构建运行时 SQLite 数据库。

输入：
  - data/raw/items/{id}.json
  - data/raw/images/{id}.png
  - data/derived/v1/{id}.json（可选）

输出：
  - data/database/dressup.db

raw 数据是可审查的数据集快照，SQLite 是可随时重新生成的运行时产物。
"""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from pathlib import Path
from typing import Any


PROJECT_DIR = Path(__file__).resolve().parents[1]
RAW_ITEMS_DIR = PROJECT_DIR / "data" / "raw" / "items"
RAW_IMAGES_DIR = PROJECT_DIR / "data" / "raw" / "images"
DESCRIPTIONS_DIR = PROJECT_DIR / "data" / "derived" / "v1"
DEFAULT_DATABASE_PATH = PROJECT_DIR / "data" / "database" / "dressup.db"
PROP_KEYS = ("elegant", "fresh", "sweet", "sexy", "cool")


SCHEMA = """
CREATE TABLE items (
    id               INTEGER PRIMARY KEY,
    name             TEXT NOT NULL,
    quality          INTEGER NOT NULL,
    type             TEXT NOT NULL,
    type_zh          TEXT NOT NULL,
    main_style       TEXT NOT NULL,
    main_style_zh    TEXT NOT NULL,
    elegant          INTEGER NOT NULL,
    fresh            INTEGER NOT NULL,
    sweet            INTEGER NOT NULL,
    sexy             INTEGER NOT NULL,
    cool             INTEGER NOT NULL,
    obtain_id        INTEGER,
    obtain_name      TEXT,
    description      TEXT,
    summary_zh       TEXT,
    category         TEXT,
    category_zh      TEXT,
    subcategory      TEXT,
    subcategory_zh   TEXT,
    image_path       TEXT NOT NULL,
    source_json_path TEXT NOT NULL,
    metadata_json    TEXT NOT NULL
);

CREATE TABLE labels (
    id   INTEGER PRIMARY KEY,
    name TEXT NOT NULL
);

CREATE TABLE item_labels (
    item_id  INTEGER NOT NULL,
    label_id INTEGER NOT NULL,
    PRIMARY KEY (item_id, label_id),
    FOREIGN KEY (item_id) REFERENCES items(id) ON DELETE CASCADE,
    FOREIGN KEY (label_id) REFERENCES labels(id) ON DELETE CASCADE
);

CREATE TABLE item_colors (
    item_id  INTEGER NOT NULL,
    position INTEGER NOT NULL,
    role     TEXT NOT NULL CHECK (role IN ('primary', 'secondary')),
    family   TEXT NOT NULL,
    hex      TEXT NOT NULL,
    red      INTEGER NOT NULL,
    green    INTEGER NOT NULL,
    blue     INTEGER NOT NULL,
    ratio    REAL NOT NULL,
    PRIMARY KEY (item_id, position),
    FOREIGN KEY (item_id) REFERENCES items(id) ON DELETE CASCADE
);

CREATE TABLE item_attributes (
    item_id  INTEGER NOT NULL,
    key      TEXT NOT NULL,
    value    TEXT NOT NULL,
    value_zh TEXT,
    PRIMARY KEY (item_id, key),
    FOREIGN KEY (item_id) REFERENCES items(id) ON DELETE CASCADE
);

CREATE TABLE outfit_items (
    outfit_id INTEGER NOT NULL,
    item_id   INTEGER NOT NULL,
    PRIMARY KEY (outfit_id, item_id),
    FOREIGN KEY (item_id) REFERENCES items(id) ON DELETE CASCADE
);

CREATE INDEX idx_items_type ON items(type);
CREATE INDEX idx_items_quality ON items(quality);
CREATE INDEX idx_items_main_style ON items(main_style);
CREATE INDEX idx_items_category ON items(category);
CREATE INDEX idx_item_labels_label ON item_labels(label_id, item_id);
CREATE INDEX idx_item_colors_family ON item_colors(family, role, item_id);
CREATE INDEX idx_item_attributes_key_value
    ON item_attributes(key, value, item_id);
CREATE INDEX idx_outfit_items_item ON outfit_items(item_id, outfit_id);
"""


def _project_relative_path(path: Path) -> str:
    """生成可跨平台写入数据库的项目相对路径。"""
    return path.resolve().relative_to(PROJECT_DIR.resolve()).as_posix()


def load_raw_items(source_dir: Path) -> list[dict[str, Any]]:
    """读取部件 JSON，并执行建库所需的基础完整性检查。"""
    files = sorted(source_dir.glob("*.json"))
    if not files:
        raise FileNotFoundError(f"目录中没有部件 JSON：{source_dir}")

    required_fields = {
        "id",
        "name",
        "quality",
        "type",
        "type_zh",
        "main_style",
        "props",
        "labels",
        "obtain",
        "metadata",
        "metadata_zh",
        "colors",
        "related_outfits",
    }
    items: list[dict[str, Any]] = []
    seen_ids: set[int] = set()

    for path in files:
        with path.open("r", encoding="utf-8") as file:
            item = json.load(file)

        missing = required_fields - set(item)
        if missing:
            raise ValueError(
                f"{path.name} 缺少字段：{', '.join(sorted(missing))}"
            )

        item_id = int(item["id"])
        if path.stem != str(item_id):
            raise ValueError(f"{path.name} 的文件名与内部 id={item_id} 不一致")
        if item_id in seen_ids:
            raise ValueError(f"发现重复部件 id：{item_id}")
        seen_ids.add(item_id)

        missing_props = set(PROP_KEYS) - set(item["props"])
        if missing_props:
            raise ValueError(
                f"{path.name} 的 props 缺少：{', '.join(sorted(missing_props))}"
            )

        item["_source_json_path"] = _project_relative_path(path)
        items.append(item)

    return items


def validate_images(items: list[dict[str, Any]], images_dir: Path) -> None:
    """要求每个部件恰好存在一张同 ID 的 PNG，并拒绝孤立图片。"""
    item_ids = {int(item["id"]) for item in items}
    image_paths = sorted(images_dir.glob("*.png"))
    if not image_paths:
        raise FileNotFoundError(f"目录中没有部件图片：{images_dir}")

    image_ids: set[int] = set()
    for path in image_paths:
        try:
            item_id = int(path.stem)
        except ValueError as error:
            raise ValueError(f"图片文件名不是数字 ID：{path.name}") from error
        if item_id in image_ids:
            raise ValueError(f"发现重复图片 ID：{item_id}")
        image_ids.add(item_id)

    missing_images = sorted(item_ids - image_ids)
    if missing_images:
        raise ValueError(f"有部件缺少图片：{missing_images[:10]}")

    orphan_images = sorted(image_ids - item_ids)
    if orphan_images:
        raise ValueError(f"有图片缺少对应部件 JSON：{orphan_images[:10]}")

    for item in items:
        item_id = int(item["id"])
        item["_image_path"] = _project_relative_path(images_dir / f"{item_id}.png")


def load_descriptions(items: list[dict[str, Any]]) -> None:
    """读取已有的离线图片描述；没有描述的部件保持为空。"""
    descriptions: dict[int, str] = {}
    for path in sorted(DESCRIPTIONS_DIR.glob("*.json")):
        item_id = int(path.stem)
        data = json.loads(path.read_text(encoding="utf-8"))
        descriptions[item_id] = data["summary_zh"]

    for item in items:
        item["_summary_zh"] = descriptions.get(int(item["id"]))


def insert_items(connection: sqlite3.Connection, items: list[dict[str, Any]]) -> None:
    """先写入部件主表，供其他关系表通过外键引用。"""
    rows = []
    for item in items:
        main_style = item["main_style"]
        props = item["props"]
        obtain = item["obtain"]
        rows.append(
            (
                int(item["id"]),
                item["name"],
                int(item["quality"]),
                item["type"],
                item["type_zh"],
                main_style["key"],
                main_style["name"],
                int(props["elegant"]),
                int(props["fresh"]),
                int(props["sweet"]),
                int(props["sexy"]),
                int(props["cool"]),
                obtain.get("id") if obtain else None,
                obtain.get("name") if obtain else None,
                item.get("description"),
                item["_summary_zh"],
                item.get("category"),
                item.get("category_zh"),
                item.get("subcategory"),
                item.get("subcategory_zh"),
                item["_image_path"],
                item["_source_json_path"],
                json.dumps(
                    item.get("metadata") or {},
                    ensure_ascii=False,
                    separators=(",", ":"),
                ),
            )
        )

    connection.executemany(
        """
        INSERT INTO items (
            id, name, quality, type, type_zh, main_style, main_style_zh,
            elegant, fresh, sweet, sexy, cool, obtain_id, obtain_name,
            description, summary_zh, category, category_zh, subcategory,
            subcategory_zh,
            image_path, source_json_path, metadata_json
        ) VALUES (
            ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?
        )
        """,
        rows,
    )


def insert_labels(connection: sqlite3.Connection, items: list[dict[str, Any]]) -> None:
    """写入标签字典和部件—标签多对多关系。"""
    label_names: dict[int, str] = {}
    item_labels: set[tuple[int, int]] = set()

    for item in items:
        item_id = int(item["id"])
        for label in item["labels"]:
            label_id = int(label["id"])
            label_name = label["name"]
            previous = label_names.setdefault(label_id, label_name)
            if previous != label_name:
                raise ValueError(
                    f"标签 {label_id} 同时出现名称 {previous!r} 和 {label_name!r}"
                )
            item_labels.add((item_id, label_id))

    connection.executemany(
        "INSERT INTO labels (id, name) VALUES (?, ?)",
        sorted(label_names.items()),
    )
    connection.executemany(
        "INSERT INTO item_labels (item_id, label_id) VALUES (?, ?)",
        sorted(item_labels),
    )


def insert_colors(connection: sqlite3.Connection, items: list[dict[str, Any]]) -> None:
    """将每个部件的一种主色和零到多种副色拆成多行。"""
    rows = []
    for item in items:
        colors = item["colors"]
        ordered_colors = [colors["primary"], *(colors.get("secondary") or [])]
        for position, color in enumerate(ordered_colors):
            rgb = color["rgb"]
            rows.append(
                (
                    int(item["id"]),
                    position,
                    color["role"],
                    color["family"],
                    color["hex"],
                    int(rgb[0]),
                    int(rgb[1]),
                    int(rgb[2]),
                    float(color["ratio"]),
                )
            )

    connection.executemany(
        """
        INSERT INTO item_colors (
            item_id, position, role, family, hex, red, green, blue, ratio
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        rows,
    )


def insert_attributes(
    connection: sqlite3.Connection, items: list[dict[str, Any]]
) -> None:
    """把不同类别才具有的 metadata 键值拆成通用属性行。"""
    rows = []
    for item in items:
        metadata = item.get("metadata") or {}
        metadata_zh = item.get("metadata_zh") or {}
        for key, value in metadata.items():
            rows.append(
                (
                    int(item["id"]),
                    key,
                    str(value),
                    str(metadata_zh[key]) if key in metadata_zh else None,
                )
            )

    connection.executemany(
        """
        INSERT INTO item_attributes (item_id, key, value, value_zh)
        VALUES (?, ?, ?, ?)
        """,
        rows,
    )


def insert_outfits(connection: sqlite3.Connection, items: list[dict[str, Any]]) -> None:
    """合并各 JSON 中重复出现的套装—部件关系。"""
    known_item_ids = {int(item["id"]) for item in items}
    rows: set[tuple[int, int]] = set()
    for item in items:
        for outfit in item.get("related_outfits") or []:
            outfit_id = int(outfit["id"])
            for item_id in outfit.get("item_ids") or []:
                related_item_id = int(item_id)
                if related_item_id not in known_item_ids:
                    raise ValueError(
                        f"套装 {outfit_id} 引用了不存在的部件 {related_item_id}"
                    )
                rows.add((outfit_id, related_item_id))

    connection.executemany(
        "INSERT INTO outfit_items (outfit_id, item_id) VALUES (?, ?)",
        sorted(rows),
    )


def build_database(
    source_dir: Path,
    images_dir: Path,
    output_path: Path,
) -> tuple[int, dict[str, int]]:
    """在临时文件中建库，全部成功后再替换正式数据库。"""
    items = load_raw_items(source_dir)
    validate_images(items, images_dir)
    load_descriptions(items)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path = output_path.with_suffix(output_path.suffix + ".tmp")
    temporary_path.unlink(missing_ok=True)

    try:
        connection = sqlite3.connect(temporary_path)
        try:
            connection.execute("PRAGMA foreign_keys = ON")
            connection.executescript(SCHEMA)
            with connection:
                insert_items(connection, items)
                insert_labels(connection, items)
                insert_colors(connection, items)
                insert_attributes(connection, items)
                insert_outfits(connection, items)

            foreign_key_errors = connection.execute(
                "PRAGMA foreign_key_check"
            ).fetchall()
            if foreign_key_errors:
                raise ValueError(f"数据库外键检查失败：{foreign_key_errors[:5]}")

            counts = {
                table: connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
                for table in (
                    "items",
                    "labels",
                    "item_labels",
                    "item_colors",
                    "item_attributes",
                    "outfit_items",
                )
            }
        finally:
            connection.close()

        temporary_path.replace(output_path)
        return len(items), counts
    except Exception:
        temporary_path.unlink(missing_ok=True)
        raise


def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="从 data/raw/items 和 data/raw/images 全量建立 SQLite 数据库。"
    )
    parser.add_argument(
        "--source",
        type=Path,
        default=RAW_ITEMS_DIR,
        help=f"部件 JSON 目录，默认 {RAW_ITEMS_DIR}",
    )
    parser.add_argument(
        "--images",
        type=Path,
        default=RAW_IMAGES_DIR,
        help=f"部件图片目录，默认 {RAW_IMAGES_DIR}",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=DEFAULT_DATABASE_PATH,
        help=f"数据库输出路径，默认 {DEFAULT_DATABASE_PATH}",
    )
    return parser.parse_args()


def main() -> int:
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")

    args = parse_arguments()
    source_dir = args.source.resolve()
    images_dir = args.images.resolve()
    output_path = args.output.resolve()

    try:
        item_count, counts = build_database(source_dir, images_dir, output_path)
    except (
        OSError,
        ValueError,
        TypeError,
        KeyError,
        json.JSONDecodeError,
        sqlite3.Error,
    ) as error:
        print(f"建库失败：{error}", file=sys.stderr)
        return 1

    print(f"数据库建立成功：{output_path}")
    print(f"校验并读取部件 JSON/图片：{item_count} 对")
    print(
        "写入记录："
        + "，".join(f"{table}={count}" for table, count in counts.items())
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
