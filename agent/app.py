"""换装推荐程序的命令行入口。"""

from __future__ import annotations

import sys

from .agent import WardrobeAgent
from .message import UserMessage


def main() -> int:
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")

    agent = WardrobeAgent()
    try:
        reply = agent.handle(UserMessage(input("请输入搭配要求：")))
    except (ValueError, RuntimeError, OSError) as error:
        print(f"推荐失败：{error}", file=sys.stderr)
        return 1

    print(f"\n解析结果：{reply.query}")
    print(reply.content)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
