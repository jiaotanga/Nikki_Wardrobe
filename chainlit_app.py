"""只展示推荐结果的 Chainlit 正式入口。"""

from pathlib import Path

import chainlit as cl

from agent.agent import WardrobeAgent
from agent.message import UserMessage
from agent.models import OutfitItem


PROJECT_DIR = Path(__file__).resolve().parent
wardrobe_agent = WardrobeAgent()


@cl.on_message
async def recommend(message: cl.Message) -> None:
    reply_message = cl.Message(content="正在解析需求并检索服装，请稍候……")
    await reply_message.send()

    try:
        reply = await cl.make_async(wardrobe_agent.handle)(
            UserMessage(message.content)
        )
    except Exception as error:
        reply_message.content = f"推荐失败：{error}"
        await reply_message.update()
        return

    if not reply.items:
        reply_message.content = "没有找到符合条件的服装。"
        await reply_message.update()
        return

    reply_message.content = "\n".join(
        f"{item.type_zh}：{item.name}　描述：{item.summary_zh or '暂无'}"
        for item in reply.items
    )
    await reply_message.update()

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
