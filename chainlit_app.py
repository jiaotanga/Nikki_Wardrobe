"""Chainlit 网页适配入口。"""

from pathlib import Path

import chainlit as cl

from agent.agent import WardrobeAgent
from agent.message import UserMessage


PROJECT_DIR = Path(__file__).resolve().parent
wardrobe_agent = WardrobeAgent()


@cl.on_message
async def recommend(message: cl.Message) -> None:
    try:
        reply = wardrobe_agent.handle(UserMessage(message.content))
    except Exception as error:
        await cl.Message(content=f"推荐失败：{error}").send()
        return

    images = []
    for item in reply.recommendation.items:
        image_path = (PROJECT_DIR / item.image_path).resolve()
        if image_path.is_file():
            images.append(
                cl.Image(
                    path=str(image_path),
                    name=f"{item.type_zh}：{item.name}",
                    display="inline",
                    size="small",
                )
            )

    await cl.Message(content=reply.content, elements=images).send()
