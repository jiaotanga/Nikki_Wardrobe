"""换装推荐程序的最小入口。"""

from __future__ import annotations

import sys

if __package__:
    from .intent_parser import parse_intent_response, request_intent_analysis
    from .recommender import recommend_complete_outfit
else:  # 允许直接运行：python agent\app.py
    from intent_parser import parse_intent_response, request_intent_analysis
    from recommender import recommend_complete_outfit


def main() -> int:
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")

    user_text = input("请输入搭配要求：").strip()

    try:
        llm_response = request_intent_analysis(user_text)
        intent = parse_intent_response(llm_response)
        outfit = recommend_complete_outfit(intent)
    except (ValueError, RuntimeError, OSError) as error:
        print(f"推荐失败：{error}", file=sys.stderr)
        return 1

    print(f"\n解析结果：{intent}")
    if outfit["complete"]:
        print("成功组成一套搭配：")
    else:
        print("无法组成完整搭配，缺少：" + "、".join(outfit["missing"]))

    for item in outfit["items"]:
        print(f"{item['type_zh']}：{item['name']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
