"""为服装部件图片生成离线文字描述。"""

from __future__ import annotations

import base64
import json
import os
import sqlite3
from pathlib import Path
from urllib.request import Request, urlopen

from dotenv import load_dotenv


ROOT = Path(__file__).resolve().parents[1]
ITEMS_DIR = ROOT / "data" / "raw" / "items"
IMAGES_DIR = ROOT / "data" / "raw" / "images"
OUTPUT_DIR = ROOT / "data" / "derived" / "v1"
DATABASE_PATH = ROOT / "data" / "database" / "dressup.db"
DEEPSEEK_BASE_URL = "https://api.deepseek.com"
DEEPSEEK_VISION_MODEL = "deepseek-v4-flash-vision-exp"

load_dotenv(ROOT / ".env")


def describe(image_path: Path, item: dict) -> dict:
    api_key = os.environ["DEEPSEEK_API_KEY"]
    image = base64.b64encode(image_path.read_bytes()).decode("ascii")
    prompt = (
        f"图片展示换装游戏中的{item['type_zh']}部件。"
        "请用一句简洁中文总结图片中明确可见的造型、图案、材质或纹理、装饰、"
        "主要颜色或渐变以及整体视觉风格；没有或无法确定的信息不要提，"
        "不要根据名称、常识或想象补充细节。只输出 JSON：{\"summary_zh\": \"...\"}。"
    )
    payload = {
        "model": DEEPSEEK_VISION_MODEL,
        "messages": [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": prompt},
                    {
                        "type": "image_url",
                        "image_url": {"url": f"data:image/png;base64,{image}"},
                    },
                ],
            }
        ],
        "response_format": {"type": "json_object"},
    }
    request = Request(
        DEEPSEEK_BASE_URL + "/chat/completions",
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    with urlopen(request, timeout=120) as response:
        content = json.load(response)["choices"][0]["message"]["content"]
    result = json.loads(content)
    return {"summary_zh": result["summary_zh"]}


def main() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    for item_path in sorted(ITEMS_DIR.glob("*.json")):
        output_path = OUTPUT_DIR / item_path.name
        if output_path.exists():
            continue
        item = json.loads(item_path.read_text(encoding="utf-8"))
        try:
            output = describe(IMAGES_DIR / f"{item['id']}.png", item)
        except json.JSONDecodeError:
            print(f"{item['id']}：DeepSeek 返回了无效 JSON，已跳过")
            continue
        output_path.write_text(
            json.dumps(output, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        print(output_path.relative_to(ROOT))

    descriptions = [
        (
            json.loads(path.read_text(encoding="utf-8"))["summary_zh"],
            int(path.stem),
        )
        for path in OUTPUT_DIR.glob("*.json")
    ]
    connection = sqlite3.connect(DATABASE_PATH)
    with connection:
        connection.executemany(
            "UPDATE items SET summary_zh = ? WHERE id = ?",
            descriptions,
        )
    connection.close()


if __name__ == "__main__":
    main()
