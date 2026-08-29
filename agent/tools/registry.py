"""Agent 工具注册器。"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any


class ToolRegistry:
    """按名称注册和调用工具。"""

    def __init__(self) -> None:
        self._tools: dict[str, Callable[..., Any]] = {}

    def register(self, name: str, tool: Callable[..., Any]) -> None:
        self._tools[name] = tool

    def call(self, name: str, *args: Any, **kwargs: Any) -> Any:
        if name not in self._tools:
            raise ValueError(f"工具未注册：{name}")
        return self._tools[name](*args, **kwargs)
