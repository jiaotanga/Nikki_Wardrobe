"""Chainlit 网页适配入口。"""

from pathlib import Path

import chainlit as cl

from agent.agent import WardrobeAgent
from agent.message import UserMessage
from agent.models import OutfitItem


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
        await cl.Message(content=header).send()
        for item in reply.items:
            image = _build_image(item)
            await cl.Message(
                content=f"{item.type_zh}：{item.name}",
                elements=[image] if image else [],
            ).send()
        return

    reply_message = cl.Message(content=reply.content)
    await reply_message.send()

    for item in reply.items:
        image = _build_image(item)
        if image:
            await image.send(for_id=reply_message.id)


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
