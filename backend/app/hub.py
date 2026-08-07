"""Fan-out of telemetry updates to every connected dashboard."""

import asyncio
import logging
from typing import Any

from fastapi import WebSocket

log = logging.getLogger(__name__)


class ConnectionHub:
    def __init__(self) -> None:
        self._clients: set[WebSocket] = set()
        self._lock = asyncio.Lock()

    async def add(self, websocket: WebSocket) -> None:
        async with self._lock:
            self._clients.add(websocket)
        log.info("dashboard connected (%d total)", len(self._clients))

    async def discard(self, websocket: WebSocket) -> None:
        async with self._lock:
            self._clients.discard(websocket)
        log.info("dashboard disconnected (%d total)", len(self._clients))

    async def broadcast(self, message: dict[str, Any]) -> None:
        async with self._lock:
            targets = list(self._clients)
        if not targets:
            return
        results = await asyncio.gather(
            *(client.send_json(message) for client in targets),
            return_exceptions=True,
        )
        # Drop anyone whose socket died between our snapshot and the send.
        dead = [c for c, r in zip(targets, results) if isinstance(r, Exception)]
        if dead:
            async with self._lock:
                self._clients.difference_update(dead)
            log.info("pruned %d dead connection(s)", len(dead))


hub = ConnectionHub()
