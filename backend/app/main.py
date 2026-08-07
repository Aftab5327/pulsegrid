import asyncio
import logging
import sys
from contextlib import asynccontextmanager

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware

from .config import CORS_ORIGINS, MQTT_HOST, MQTT_PORT, TELEMETRY_WILDCARD
from .hub import hub
from .mqtt_client import run_mqtt_ingest
from .state import store

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger("digispace")

# aiomqtt's transport needs the selector loop on Windows; uvicorn defaults to proactor.
if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())


@asynccontextmanager
async def lifespan(app: FastAPI):
    task = asyncio.create_task(run_mqtt_ingest(), name="mqtt-ingest")
    log.info("DigiSpace backend up; broker %s:%d", MQTT_HOST, MQTT_PORT)
    try:
        yield
    finally:
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass
        log.info("DigiSpace backend down")


app = FastAPI(title="DigiSpace Telemetry API", version="1.0.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/api/health")
async def health() -> dict:
    return {"status": "ok", "broker": f"{MQTT_HOST}:{MQTT_PORT}", "topic": TELEMETRY_WILDCARD}


@app.get("/api/snapshot")
async def snapshot() -> dict:
    """Current value of every card. Same payload the WebSocket sends on connect."""
    return store.snapshot().model_dump()


@app.websocket("/ws/telemetry")
async def telemetry(websocket: WebSocket) -> None:
    await websocket.accept()
    await hub.add(websocket)
    try:
        await websocket.send_json({"type": "snapshot", "data": store.snapshot().model_dump()})
        while True:
            # The dashboard is receive-only; this read exists to notice disconnects.
            await websocket.receive_text()
    except WebSocketDisconnect:
        pass
    finally:
        await hub.discard(websocket)
