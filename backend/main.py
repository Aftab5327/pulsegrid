"""DigiSpace telemetry backend.

    simulated sensors --MQTT--> broker --MQTT--> this --WebSocket--> dashboard

Subscribes to `digispace/sensors/+/telemetry`, keeps the latest reading and a
rolling history per metric in memory, and pushes every new reading to connected
dashboards.

Run it:

    python main.py

Prefer that over `uvicorn main:app`. On Windows the default event loop is the
proactor loop, which has no add_reader/add_writer; aiomqtt's transport needs
them. The `__main__` block below sets the selector policy before uvicorn builds
its loop — doing it at import time is too late, because uvicorn imports this
module from inside an already-running loop.

Configuration, all optional, via environment:

    MQTT_HOST           broker hostname             default localhost
    MQTT_PORT           broker port                 default 1883
    MQTT_TOPIC          topic filter to subscribe   default digispace/sensors/+/telemetry
    HISTORY_SIZE        readings kept per metric    default 120
    CORS_ORIGINS        comma-separated origins     default http://localhost:5173
"""

from __future__ import annotations

import asyncio
import logging
import os
import sys
from collections import deque
from contextlib import asynccontextmanager
from typing import Any

import aiomqtt
from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, ValidationError

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger("digispace")

# --- configuration -----------------------------------------------------------

MQTT_HOST = os.getenv("MQTT_HOST", "localhost")
MQTT_PORT = int(os.getenv("MQTT_PORT", "1883"))
MQTT_TOPIC = os.getenv("MQTT_TOPIC", "digispace/sensors/+/telemetry")
HISTORY_SIZE = int(os.getenv("HISTORY_SIZE", "120"))
CORS_ORIGINS = [
    origin.strip()
    for origin in os.getenv("CORS_ORIGINS", "http://localhost:5173").split(",")
    if origin.strip()
]

RECONNECT_SECONDS = 5


# --- model -------------------------------------------------------------------


class Reading(BaseModel):
    """One sensor telemetry message. Anything that fails to parse is dropped."""

    sensor_id: str
    metric: str
    value: float
    unit: str
    site: str
    ts: str


# --- in-memory store ---------------------------------------------------------


class TelemetryStore:
    """Latest reading per metric, plus the last HISTORY_SIZE readings.

    Not persisted: everything resets when the process restarts. `deque` with a
    maxlen does the eviction, so history is O(1) per insert and cannot grow
    without bound however long the process runs.
    """

    def __init__(self, history_size: int = HISTORY_SIZE) -> None:
        self._history_size = history_size
        self.latest: dict[str, Reading] = {}
        self.history: dict[str, deque[Reading]] = {}

    def add(self, reading: Reading) -> None:
        self.latest[reading.metric] = reading
        if reading.metric not in self.history:
            self.history[reading.metric] = deque(maxlen=self._history_size)
        self.history[reading.metric].append(reading)

    def snapshot(self) -> dict[str, dict[str, Any]]:
        return {metric: reading.model_dump() for metric, reading in self.latest.items()}

    def metrics(self) -> list[str]:
        return sorted(self.latest)


store = TelemetryStore()


# --- websocket fan-out -------------------------------------------------------


class ConnectionManager:
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
        # Drop anyone whose socket died between the snapshot above and the send.
        dead = [client for client, result in zip(targets, results) if isinstance(result, Exception)]
        if dead:
            async with self._lock:
                self._clients.difference_update(dead)
            log.info("pruned %d dead connection(s)", len(dead))


manager = ConnectionManager()


# --- mqtt ingest -------------------------------------------------------------


async def handle_message(topic: str, payload: bytes) -> None:
    """Validate one MQTT message, store it, fan it out.

    A bad payload is logged and dropped: one misbehaving sensor must not take
    the ingest loop down with it. Pydantic wraps malformed JSON in
    ValidationError too, so this one branch covers both bad syntax and the
    right JSON in the wrong shape.
    """
    try:
        reading = Reading.model_validate_json(payload)
    except ValidationError as exc:
        log.warning("ignoring malformed payload on %s: %d error(s)", topic, exc.error_count())
        return

    store.add(reading)
    await manager.broadcast({"type": "reading", "data": reading.model_dump()})


async def mqtt_listener() -> None:
    """Subscribe and stay subscribed. Reconnects forever; never raises."""
    while True:
        try:
            async with aiomqtt.Client(hostname=MQTT_HOST, port=MQTT_PORT) as client:
                await client.subscribe(MQTT_TOPIC)
                log.info("subscribed to %s on %s:%d", MQTT_TOPIC, MQTT_HOST, MQTT_PORT)
                await manager.broadcast({"type": "broker", "connected": True})

                async for message in client.messages:
                    await handle_message(str(message.topic), message.payload)

        except asyncio.CancelledError:
            # Shutdown, not an error — let it propagate so the task ends.
            raise
        except aiomqtt.MqttError as exc:
            log.warning("MQTT connection lost (%s); retrying in %ds", exc, RECONNECT_SECONDS)
            await manager.broadcast({"type": "broker", "connected": False})
            await asyncio.sleep(RECONNECT_SECONDS)
        except Exception:
            # Anything unexpected: log with traceback and keep the loop alive.
            log.exception("unexpected error in MQTT listener; retrying in %ds", RECONNECT_SECONDS)
            await asyncio.sleep(RECONNECT_SECONDS)


# --- app ---------------------------------------------------------------------


@asynccontextmanager
async def lifespan(app: FastAPI):
    task = asyncio.create_task(mqtt_listener(), name="mqtt-listener")
    log.info("backend up; broker %s:%d", MQTT_HOST, MQTT_PORT)
    try:
        yield
    finally:
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass
        log.info("backend down")


app = FastAPI(title="DigiSpace Telemetry API", version="1.0.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/")
async def health() -> dict:
    return {
        "status": "ok",
        "broker": f"{MQTT_HOST}:{MQTT_PORT}",
        "topic": MQTT_TOPIC,
        "metrics": store.metrics(),
        "history_size": HISTORY_SIZE,
    }


@app.get("/api/latest")
async def latest() -> dict:
    """Most recent reading for every metric seen so far."""
    return store.snapshot()


@app.get("/api/history/{metric}")
async def history(metric: str) -> dict:
    """Up to the last HISTORY_SIZE readings for one metric, oldest first."""
    readings = store.history.get(metric)
    if readings is None:
        raise HTTPException(
            status_code=404,
            detail=f"unknown metric '{metric}'; known metrics: {store.metrics()}",
        )
    return {
        "metric": metric,
        "count": len(readings),
        "readings": [reading.model_dump() for reading in readings],
    }


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket) -> None:
    await websocket.accept()
    await manager.add(websocket)
    try:
        await websocket.send_json({"type": "snapshot", "data": store.snapshot()})
        while True:
            # The dashboard is receive-only; this read is here to notice the
            # client going away, and to drain anything it does send.
            await websocket.receive_text()
    except WebSocketDisconnect:
        pass
    finally:
        await manager.discard(websocket)


if __name__ == "__main__":
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

    import uvicorn

    uvicorn.run(
        app,
        host=os.getenv("HOST", "127.0.0.1"),
        port=int(os.getenv("PORT", "8000")),
        loop="asyncio",
    )
