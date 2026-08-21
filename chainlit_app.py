"""Chainlit 网页入口。"""

from pathlib import Path

import chainlit as cl

from agent.intent_parser import parse_intent_response, request_intent_analysis
from agent.recommender import recommend_complete_outfit


PROJECT_DIR = Path(__file__).resolve().parent


@cl.on_message
async def recommend(message: cl.Message) -> None:
    """把一条用户需求转换为一套文字搭配。"""
    try:
        llm_response = request_intent_analysis(message.content)
        intent = parse_intent_response(llm_response)
        outfit = recommend_complete_outfit(intent)
    except Exception as error:
        await cl.Message(content=f"推荐失败：{error}").send()
        return

    if outfit["complete"]:
        lines = ["为你推荐以下搭配："]
    else:
        missing = "、".join(outfit["missing"])
        lines = [f"暂时无法组成完整搭配（缺少：{missing}），已有部件如下："]

    images = []
    for item in outfit["items"]:
        lines.append(f"- {item['type_zh']}：{item['name']}")
        image_path = (PROJECT_DIR / item["image_path"]).resolve()
        if image_path.is_file():
            images.append(
                cl.Image(
                    path=str(image_path),
                    name=f"{item['type_zh']}：{item['name']}",
                    display="inline",
                    size="small",
                )
            )

    if not outfit["items"]:
        lines.append("没有找到符合条件的部件。")

    await cl.Message(content="\n".join(lines), elements=images).send()
