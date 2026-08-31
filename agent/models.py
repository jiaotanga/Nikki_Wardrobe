"""穿搭推荐领域对象。"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Intent:
    """用户的结构化穿搭要求；None 表示未指定。"""

    main_style: str | None = None
    quality: int | None = None
    primary_color: str | None = None
    style_label: str | None = None


@dataclass(frozen=True)
class PlanStep:
    """Planner 生成的一步穿搭操作。"""

    action: str
    item_type: str | None
    intent: Intent


@dataclass(frozen=True)
class Plan:
    """WardrobeAgent 需要顺序执行的操作。"""

    steps: tuple[PlanStep, ...]


@dataclass(frozen=True)
class OutfitItem:
    """一件可用于搭配的服装部件。"""

    id: int
    name: str
    quality: int
    type: str
    type_zh: str
    main_style: str
    main_style_zh: str
    primary_color: str
    primary_color_hex: str
    style_labels: tuple[str, ...]
    image_path: str


@dataclass(frozen=True)
class OutfitRecommendation:
    """一次完整穿搭推荐结果。"""

    complete: bool
    missing: tuple[str, ...]
    garment_structure: str | None
    candidate_count: int
    items: tuple[OutfitItem, ...]
