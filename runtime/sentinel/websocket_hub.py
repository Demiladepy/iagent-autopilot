"""WebSocket fan-out — drop dead clients without affecting others."""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from fastapi import WebSocket
from starlette.websockets import WebSocketDisconnect, WebSocketState

logger = logging.getLogger(__name__)


class WebSocketHub:
    """Broadcast bus events to all connected dashboard clients."""

    def __init__(self) -> None:
        self._clients: set[WebSocket] = set()
        self._lock = asyncio.Lock()

    @property
    def client_count(self) -> int:
        return len(self._clients)

    async def register(self, websocket: WebSocket) -> None:
        async with self._lock:
            self._clients.add(websocket)

    async def unregister(self, websocket: WebSocket) -> None:
        async with self._lock:
            self._clients.discard(websocket)

    async def broadcast(self, message: dict[str, Any]) -> None:
        async with self._lock:
            clients = list(self._clients)
        if not clients:
            return

        dead: list[WebSocket] = []
        for ws in clients:
            try:
                if ws.client_state != WebSocketState.CONNECTED:
                    dead.append(ws)
                    continue
                await ws.send_json(message)
            except WebSocketDisconnect:
                dead.append(ws)
            except Exception as exc:
                logger.debug("WebSocket send failed, dropping client: %s", exc)
                dead.append(ws)

        if dead:
            async with self._lock:
                for ws in dead:
                    self._clients.discard(ws)

    async def run_fanout(self, bus: Any) -> None:
        """Subscribe to all bus topics and broadcast to WebSocket clients."""
        try:
            async for event in bus.subscribe("*"):
                await self.broadcast(event)
        except asyncio.CancelledError:
            raise
