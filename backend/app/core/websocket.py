"""Redis-backed WebSocket manager — replaces ``frappe.publish_realtime()``.

Each backend instance keeps its local socket connections and subscribes to a
Redis channel per company, so events published from any instance (or from a
scheduler job) reach every connected client of that tenant.

MANUAL_REVIEW: Redis Pub/Sub assumed for realtime (Section 7, item 7).
"""

import asyncio
import contextlib
import json
import uuid
from typing import Any

import redis.asyncio as aioredis
from fastapi import WebSocket

from app.core.config import get_settings
from app.core.logging import get_logger

logger = get_logger(__name__)

_CHANNEL_PREFIX = "realtime:company:"


class WebSocketManager:
    def __init__(self) -> None:
        self._connections: dict[uuid.UUID, set[WebSocket]] = {}
        self._redis: aioredis.Redis | None = None
        self._listener_task: asyncio.Task[None] | None = None

    async def startup(self) -> None:
        self._redis = aioredis.from_url(get_settings().redis_url, decode_responses=True)
        self._listener_task = asyncio.create_task(self._listen())

    async def shutdown(self) -> None:
        if self._listener_task:
            self._listener_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._listener_task
        if self._redis:
            await self._redis.aclose()

    async def connect(self, websocket: WebSocket, company_id: uuid.UUID) -> None:
        await websocket.accept()
        self._connections.setdefault(company_id, set()).add(websocket)

    def disconnect(self, websocket: WebSocket, company_id: uuid.UUID) -> None:
        self._connections.get(company_id, set()).discard(websocket)

    async def publish(self, company_id: uuid.UUID, event: str, payload: dict[str, Any]) -> None:
        """Publish an event to all clients of a company across all instances."""
        if self._redis is None:
            return
        await self._redis.publish(
            f"{_CHANNEL_PREFIX}{company_id}", json.dumps({"event": event, "payload": payload})
        )

    async def _listen(self) -> None:
        assert self._redis is not None
        pubsub = self._redis.pubsub()
        await pubsub.psubscribe(f"{_CHANNEL_PREFIX}*")
        async for message in pubsub.listen():
            if message["type"] != "pmessage":
                continue
            try:
                company_id = uuid.UUID(message["channel"].removeprefix(_CHANNEL_PREFIX))
                data = message["data"]
                for ws in list(self._connections.get(company_id, ())):
                    await ws.send_text(data)
            except Exception:  # noqa: BLE001 — a bad client must not kill the listener
                logger.exception("websocket_broadcast_failed")


ws_manager = WebSocketManager()
