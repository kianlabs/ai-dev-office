"""Tool abstraction.

In the MVP every tool is a deterministic stub (no autonomous shell execution
by design). The interface is the contract later runtimes bound to real tools:
each executor receives a :class:`ToolChest` and calls tools through ``call()``.
"""

from __future__ import annotations

import asyncio
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any


@dataclass
class ToolResult:
    ok: bool
    output: str = ""
    meta: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {"ok": self.ok, "output": self.output, "meta": self.meta}


class BaseTool(ABC):
    name: str
    description: str = ""

    @abstractmethod
    async def run(self, **kwargs: Any) -> ToolResult:
        ...

    async def call(self, **kwargs: Any) -> ToolResult:
        t0 = time.time()
        result = await self.run(**kwargs)
        result.meta["elapsed_ms"] = int((time.time() - t0) * 1000)
        return result


class ToolChest:
    """A per-executor bag of tools a runtime may call."""

    def __init__(self, tools: list[BaseTool] | None = None) -> None:
        self._tools: dict[str, BaseTool] = {}
        for tool in tools or []:
            self.register(tool)

    def register(self, tool: BaseTool) -> None:
        self._tools[tool.name] = tool

    def has(self, name: str) -> bool:
        return name in self._tools

    async def call_tool(self, name: str, **kwargs: Any) -> ToolResult:
        tool = self._tools.get(name)
        if tool is None:
            return ToolResult(ok=False, output=f"Unknown tool: {name}")
        try:
            return await tool.call(**kwargs)
        except Exception as err:  # noqa: BLE001
            return ToolResult(ok=False, output=f"Tool error: {err}")

    def names(self) -> list[str]:
        return list(self._tools)


async def delay(seconds: float) -> None:
    await asyncio.sleep(seconds)