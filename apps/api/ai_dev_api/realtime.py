"""Realtime bus: keeps websocket clients updated with the engine's stream."""

from __future__ import annotations

import asyncio
from typing import Any

from fastapi import WebSocket


class RealtimeBus:
    def __init__(self) -> None:
        self._connections: set[WebSocket] = set()

    async def connect(self, ws: WebSocket) -> None:
        await ws.accept()
        self._connections.add(ws)

    async def disconnect(self, ws: WebSocket) -> None:
        self._connections.discard(ws)

    async def broadcast(self, message: dict[str, Any]) -> None:
        if not self._connections:
            return

        async def _send(ws: WebSocket) -> None:
            try:
                await ws.send_json(message)
            except Exception:  # noqa: BLE001 - stale socket
                self._connections.discard(ws)

        await asyncio.gather(*[_send(ws) for ws in list(self._connections)])