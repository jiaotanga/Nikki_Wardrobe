"""Chainlit 网页适配入口。"""

import json
from pathlib import Path

import chainlit as cl

from agent.agent import WardrobeAgent
from agent.message import UserMessage
from agent.models import ItemRequest, OutfitItem, WardrobeQuery


PROJECT_DIR = Path(__file__).resolve().parent
wardrobe_agent = WardrobeAgent()


@cl.on_message
async def recommend(message: cl.Message) -> None:
    try:
        reply = wardrobe_agent.handle(UserMessage(message.content))
    except Exception as error:
        await cl.Message(content=f"推荐失败：{error}").send()
        return

    if reply.display_mode == "item_list":
        header = reply.content.splitlines()[0]
        await cl.Message(content=f"{header}\n\n{_format_query(reply.query)}").send()
        for item in reply.items:
            image = _build_image(item)
            await cl.Message(
                content=(
                    f"{item.type_zh}：{item.name}\n"
                    f"编号：{item.id}\n"
                    f"描述：{item.summary_zh or '暂无'}"
                ),
                elements=[image] if image else [],
            ).send()
        return

    reply_message = cl.Message(
        content=(
            f"{_format_query(reply.query)}"
            f"{_format_item_requests(reply.item_requests)}\n\n"
            f"{reply.content}"
        )
    )
    await reply_message.send()

    for item in reply.items:
        image = _build_image(item)
        if image:
            await image.send(for_id=reply_message.id)


def _format_query(query: WardrobeQuery) -> str:
    return (
        f"main_style：{query.main_style or 'null'}\n"
        f"quality：{query.quality if query.quality is not None else 'null'}\n"
        f"primary_color：{query.primary_color or 'null'}\n"
        f"item_name：{query.item_name or 'null'}\n"
        f"semantic_query：{query.semantic_query or 'null'}\n"
        f"keywords：{json.dumps(query.keywords, ensure_ascii=False)}"
    )


def _format_item_requests(item_requests: tuple[ItemRequest, ...]) -> str:
    if not item_requests:
        return ""
    lines = ["\n指定部件条件："]
    for request in item_requests:
        query = request.query
        conditions = {
            "main_style": query.main_style,
            "quality": query.quality,
            "primary_color": query.primary_color,
            "item_name": query.item_name,
            "semantic_query": query.semantic_query,
            "keywords": query.keywords,
        }
        lines.append(
            f"- {request.item_type or '未指定类别'}："
            f"{json.dumps(conditions, ensure_ascii=False)}"
        )
    return "\n".join(lines)


def _build_image(item: OutfitItem) -> cl.Image | None:
    image_path = (PROJECT_DIR / item.image_path).resolve()
    if not image_path.is_file():
        return None
    return cl.Image(
        path=str(image_path),
        name=f"{item.type_zh}：{item.name}",
        display="inline",
        size="small",
    )
