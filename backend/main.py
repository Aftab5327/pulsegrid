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
import json
import logging
import math
import os
import re
import sys
import ssl
from collections import deque
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import Any

import aiomqtt
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Query, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from influxdb_client import InfluxDBClient, Point, WriteOptions
from influxdb_client.client.write_api import WriteType
from pydantic import BaseModel, ConfigDict, ValidationError

# Load .env before any os.getenv below reads configuration.
load_dotenv()

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger("digispace")

# --- configuration -----------------------------------------------------------

MQTT_HOST = os.getenv("MQTT_HOST", "localhost")
MQTT_PORT = int(os.getenv("MQTT_PORT", "1883"))
MQTT_USERNAME = os.getenv("MQTT_USERNAME")
MQTT_PASSWORD = os.getenv("MQTT_PASSWORD")
MQTT_TLS = os.getenv("MQTT_TLS", "false").lower() == "true"
MQTT_TOPIC = os.getenv("MQTT_TOPIC", "digispace/sensors/+/telemetry")
# Prefix for outbound control topics: <prefix>/sensors/<sensor_id>/command.
# Same prefix the simulator publishes telemetry under.
MQTT_TOPIC_PREFIX = os.getenv("MQTT_TOPIC_PREFIX", "digispace")
COMMAND_TEMPLATE = f"{MQTT_TOPIC_PREFIX}/sensors/{{sensor_id}}/command"
HISTORY_SIZE = int(os.getenv("HISTORY_SIZE", "120"))
SITE_ID = os.getenv("SITE_ID", "building-1")
CORS_ORIGINS = [
    origin.strip()
    for origin in os.getenv("CORS_ORIGINS", "http://localhost:5173").split(",")
    if origin.strip()
]

RECONNECT_SECONDS = 5

# --- InfluxDB ----------------------------------------------------------------
#
# Every setting comes from the environment (see .env.example). Nothing is
# hardcoded: with no .env the values are empty, persistence stays switched off,
# and the live MQTT -> WebSocket path runs exactly as before.
INFLUX_URL = os.getenv("INFLUX_URL", "")
INFLUX_ORG = os.getenv("INFLUX_ORG", "")
INFLUX_BUCKET = os.getenv("INFLUX_BUCKET", "")
INFLUX_TOKEN = os.getenv("INFLUX_TOKEN", "")

MEASUREMENT = "telemetry"
MIX_MEASUREMENT = "carbon_mix"

# Metrics the API recognises. Used for the 404 on /api/history/{metric}: with
# history now in Influx, validity is a fixed set rather than "seen this run".
KNOWN_METRICS = ("lights", "water", "carbon", "energy", "footfall")

# Accepted ?range= values. Strict, because this string is interpolated into a
# Flux query — anything unmatched is rejected rather than escaped.
RANGE_PATTERN = re.compile(r"^(\d{1,4})([smhdw])$")
RANGE_UNIT_SECONDS = {"s": 1, "m": 60, "h": 3600, "d": 86400, "w": 604800}
DEFAULT_RANGE = "1h"
# Cap on points returned; aggregateWindow widens to keep under this.
TARGET_POINTS = 360


# --- model -------------------------------------------------------------------


class Reading(BaseModel):
    """One sensor telemetry message. Anything that fails to parse is dropped."""

    sensor_id: str
    metric: str
    value: float
    unit: str
    site: str
    ts: str
    # Only the carbon sensor publishes a generation mix. Optional so the other
    # four sensors, which omit the key entirely, still validate.
    mix: dict[str, float] | None = None
    # Controllable devices echo their state back in telemetry, so the UI can
    # reconcile its optimistic controls against what the device actually did.
    on: bool | None = None
    target: float | None = None


class Command(BaseModel):
    """A control command for one device.

    `extra="forbid"` so a typo is a 422 rather than a command that silently
    does nothing after a round trip through the broker.
    """

    model_config = ConfigDict(extra="forbid")

    on: bool | None = None
    target: float | None = None


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


# --- InfluxDB persistence ----------------------------------------------------


def parse_range(value: str) -> int | None:
    """Seconds for a range like '15m' or '7d', or None if it is not valid."""
    match = RANGE_PATTERN.match(value)
    if not match:
        return None
    amount, unit = match.groups()
    seconds = int(amount) * RANGE_UNIT_SECONDS[unit]
    return seconds or None


class InfluxStore:
    """Persistence for telemetry. Every method is best-effort.

    InfluxDB being down must never take the live path with it, so nothing here
    raises: failures are logged and reported through `healthy`. The caller keeps
    running on the in-memory store.

    Writes use the batching writer, which hands off to a background worker
    thread, so `write()` returns immediately and never blocks the event loop.
    Queries are blocking, so callers run them via asyncio.to_thread.
    """

    def __init__(self) -> None:
        self._client: InfluxDBClient | None = None
        self._write_api: Any = None
        self.configured = bool(INFLUX_URL and INFLUX_ORG and INFLUX_BUCKET and INFLUX_TOKEN)
        self.healthy = False
        self.last_error: str | None = None

    def connect(self) -> bool:
        if not self.configured:
            self.last_error = "not configured (INFLUX_URL/ORG/BUCKET/TOKEN)"
            log.warning("InfluxDB %s; running without persistence", self.last_error)
            return False
        try:
            self._client = InfluxDBClient(url=INFLUX_URL, token=INFLUX_TOKEN, org=INFLUX_ORG)
            self._write_api = self._client.write_api(
                write_options=WriteOptions(
                    write_type=WriteType.batching,
                    batch_size=200,
                    flush_interval=1_000,
                    max_retries=3,
                    retry_interval=2_000,
                )
            )
            self.healthy = bool(self._client.ping())
            self.last_error = None if self.healthy else "ping failed"
        except Exception as exc:  # any client/transport error
            self.healthy = False
            self.last_error = str(exc)

        if self.healthy:
            log.info("InfluxDB connected: %s org=%s bucket=%s", INFLUX_URL, INFLUX_ORG, INFLUX_BUCKET)
        else:
            log.warning(
                "InfluxDB unreachable (%s); history falls back to memory", self.last_error
            )
        return self.healthy

    def ping(self) -> bool:
        if not self._client:
            return False
        try:
            self.healthy = bool(self._client.ping())
            if self.healthy:
                self.last_error = None
        except Exception as exc:
            self.healthy = False
            self.last_error = str(exc)
        return self.healthy

    def write_reading(self, reading: "Reading") -> None:
        """Queue one reading, plus its mix if it carries one. Never raises."""
        if not self._write_api:
            return
        try:
            timestamp = datetime.fromisoformat(reading.ts.replace("Z", "+00:00"))
        except ValueError:
            timestamp = datetime.now(timezone.utc)

        try:
            points = [
                Point(MEASUREMENT)
                .tag("metric", reading.metric)
                .tag("sensor_id", reading.sensor_id)
                .tag("site", reading.site)
                .field("value", float(reading.value))
                .time(timestamp)
            ]

            # Carbon also persists its generation mix, one field per source, so
            # the breakdown survives a restart alongside the intensity.
            if reading.mix:
                mix_point = (
                    Point(MIX_MEASUREMENT)
                    .tag("sensor_id", reading.sensor_id)
                    .tag("site", reading.site)
                    .time(timestamp)
                )
                for source, share in reading.mix.items():
                    mix_point = mix_point.field(source, float(share))
                points.append(mix_point)

            self._write_api.write(bucket=INFLUX_BUCKET, org=INFLUX_ORG, record=points)
        except Exception as exc:
            if self.healthy:  # log the transition, not every dropped point
                log.warning("InfluxDB write failed (%s); continuing", exc)
            self.healthy = False
            self.last_error = str(exc)

    def query_history(self, metric: str, seconds: int) -> list[dict[str, Any]] | None:
        """Readings for one metric, oldest first. None means the query failed.

        `metric` is validated against KNOWN_METRICS by the caller and the range
        against RANGE_PATTERN, so neither can inject into the Flux below.
        """
        if not self._client:
            return None

        # Widen the aggregation window with the range so a 7d chart returns a
        # few hundred points rather than hundreds of thousands.
        every = max(1, math.ceil(seconds / TARGET_POINTS))
        flux = f'''
from(bucket: "{INFLUX_BUCKET}")
  |> range(start: -{seconds}s)
  |> filter(fn: (r) => r._measurement == "{MEASUREMENT}")
  |> filter(fn: (r) => r.metric == "{metric}")
  |> filter(fn: (r) => r._field == "value")
  |> aggregateWindow(every: {every}s, fn: mean, createEmpty: false)
  |> keep(columns: ["_time", "_value"])
  |> sort(columns: ["_time"])
'''
        try:
            tables = self._client.query_api().query(flux, org=INFLUX_ORG)
        except Exception as exc:
            if self.healthy:
                log.warning("InfluxDB query failed (%s); falling back to memory", exc)
            self.healthy = False
            self.last_error = str(exc)
            return None

        self.healthy = True
        readings: list[dict[str, Any]] = []
        for table in tables:
            for record in table.records:
                value = record.get_value()
                if value is None:
                    continue
                moment = record.get_time()
                readings.append(
                    {
                        "ts": moment.isoformat().replace("+00:00", "Z"),
                        "value": float(value),
                    }
                )
        return readings

    def close(self) -> None:
        try:
            if self._write_api:
                self._write_api.close()  # flushes anything still queued
            if self._client:
                self._client.close()
        except Exception as exc:
            log.warning("InfluxDB shutdown error (%s)", exc)


influx = InfluxStore()


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
    # Persistence is a side effect of the live path, never a gate on it: the
    # batching writer only enqueues, and InfluxStore swallows its own errors.
    influx.write_reading(reading)
    await manager.broadcast({"type": "reading", "data": reading.model_dump()})
RUN_SIMULATOR = os.getenv("RUN_SIMULATOR", "false").lower() == "true"

async def simulator_task() -> None:
    """Publishes simulated sensor telemetry, running only when RUN_SIMULATOR=true
    (used on Render's free tier, where we can't run a separate worker process)."""
    import random
    from datetime import datetime, timezone

    sensors = [
        {"sensor_id": "lights-01", "metric": "lights", "unit": "k", "value": 4300, "low": 2700, "high": 5000, "step": 60},
        {"sensor_id": "water-01", "metric": "water", "unit": "m3", "value": 8.42, "low": 5.0, "high": 12.0, "step": 0.15},
        {"sensor_id": "energy-01", "metric": "energy", "unit": "kWh", "value": 4300, "low": 2000, "high": 6000, "step": 120},
        {"sensor_id": "footfall-01", "metric": "footfall", "unit": "people", "value": 110, "low": 40, "high": 160, "step": 8},
    ]
    mix = {"solar": 15.0, "wind": 15.0, "nuclear": 20.0, "hydro": 20.0, "coal": 30.0}
    factors = {"solar": 48.0, "wind": 11.0, "nuclear": 12.0, "hydro": 24.0, "coal": 820.0}

    while True:
        try:
            tls_params = (
                aiomqtt.TLSParameters(cert_reqs=ssl.CERT_REQUIRED) if MQTT_TLS else None
            )
            async with aiomqtt.Client(
                hostname=MQTT_HOST,
                port=MQTT_PORT,
                username=MQTT_USERNAME,
                password=MQTT_PASSWORD,
                tls_params=tls_params,
                identifier="pulsegrid-simulator",
            ) as client:
                log.info("simulator: connected, publishing to %s", MQTT_TOPIC_PREFIX)
                while True:
                    for s in sensors:
                        s["value"] += random.uniform(-s["step"], s["step"])
                        s["value"] = max(s["low"], min(s["high"], s["value"]))
                        payload = {
                            "sensor_id": s["sensor_id"],
                            "metric": s["metric"],
                            "value": round(s["value"], 2),
                            "unit": s["unit"],
                            "site": SITE_ID,
                            "ts": datetime.now(timezone.utc).isoformat(),
                        }
                        topic = f"{MQTT_TOPIC_PREFIX}/sensors/{s['sensor_id']}/telemetry"
                        await client.publish(topic, json.dumps(payload), qos=0)

                    for k in mix:
                        mix[k] = max(0.5, mix[k] + random.uniform(-1.5, 1.5))
                    total = sum(mix.values())
                    mix_norm = {k: round(v * 100 / total, 1) for k, v in mix.items()}
                    intensity = sum(mix_norm[k] / 100 * factors[k] for k in mix_norm)
                    carbon_payload = {
                        "sensor_id": "carbon-01",
                        "metric": "carbon",
                        "value": round(intensity, 1),
                        "unit": "gCO2/kWh",
                        "site": SITE_ID,
                        "ts": datetime.now(timezone.utc).isoformat(),
                        "mix": mix_norm,
                    }
                    await client.publish(
                        f"{MQTT_TOPIC_PREFIX}/sensors/carbon-01/telemetry",
                        json.dumps(carbon_payload),
                        qos=0,
                    )
                    await asyncio.sleep(2)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            log.warning("simulator: connection error (%s); retrying in 5s", exc)
            await asyncio.sleep(5)


async def mqtt_listener() -> None:
    """Subscribe and stay subscribed. Reconnects forever; never raises."""
    while True:
        try:
            async with aiomqtt.Client(
            hostname=MQTT_HOST,
            port=MQTT_PORT,
            username=MQTT_USERNAME,
            password=MQTT_PASSWORD,
            tls_params=aiomqtt.TLSParameters(cert_reqs=ssl.CERT_REQUIRED) if MQTT_TLS else None,
            identifier="pulsegrid-backend",
            ) as client:
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
    # Connecting is blocking and may hang on an unreachable host, so it runs off
    # the event loop. A failure here is logged, not fatal.
    await asyncio.to_thread(influx.connect)

    tasks = [asyncio.create_task(mqtt_listener(), name="mqtt-listener")]
    if RUN_SIMULATOR:
        tasks.append(asyncio.create_task(simulator_task(), name="simulator"))
        log.info("simulator task enabled (RUN_SIMULATOR=true)")
        log.info("backend up; broker %s:%d", MQTT_HOST, MQTT_PORT)
    try:
        yield
    finally:
        for t in tasks:
            t.cancel()
        for t in tasks:
            try:
                await t
            except asyncio.CancelledError:
                pass
        await asyncio.to_thread(influx.close)
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
    if influx.configured:
        reachable = await asyncio.to_thread(influx.ping)
        influx_status = "ok" if reachable else "unreachable"
    else:
        influx_status = "not configured"

    return {
        "status": "ok",
        "broker": f"{MQTT_HOST}:{MQTT_PORT}",
        "topic": MQTT_TOPIC,
        "metrics": store.metrics(),
        "history_size": HISTORY_SIZE,
        "influx": {
            "status": influx_status,
            "url": INFLUX_URL or None,
            "bucket": INFLUX_BUCKET or None,
            "error": influx.last_error,
        },
    }


@app.get("/api/latest")
async def latest() -> dict:
    """Most recent reading for every metric seen so far."""
    return store.snapshot()


@app.get("/api/history/{metric}")
async def history(
    metric: str,
    range: str = Query(DEFAULT_RANGE, description="Window to query, e.g. 15m, 1h, 24h, 7d"),
) -> dict:
    """Readings for one metric over `range`, oldest first, as {ts, value}.

    Served from InfluxDB. If Influx is unreachable this degrades to the
    in-memory window rather than failing, so charts keep drawing.
    """
    if metric not in KNOWN_METRICS:
        raise HTTPException(
            status_code=404,
            detail=f"unknown metric '{metric}'; known metrics: {list(KNOWN_METRICS)}",
        )

    seconds = parse_range(range)
    if seconds is None:
        raise HTTPException(
            status_code=400,
            detail=f"invalid range '{range}'; expected a number followed by s, m, h, d or w",
        )

    readings = await asyncio.to_thread(influx.query_history, metric, seconds)

    source = "influxdb"
    if readings is None:
        # Influx down or unconfigured: serve what memory still holds.
        source = "memory"
        buffered = store.history.get(metric, ())
        readings = [{"ts": item.ts, "value": item.value} for item in buffered]

    return {
        "metric": metric,
        "range": range,
        "source": source,
        "count": len(readings),
        "readings": readings,
    }


def resolve_sensor_id(device: str) -> str | None:
    """Map a path segment to a real sensor_id.

    Accepts either a metric name ("lights") or a sensor_id ("lights-01"), so
    the frontend can address devices by the metric it already knows. The
    mapping comes from telemetry we have actually seen rather than a hardcoded
    table, so it stays correct if devices are renamed or added.
    """
    for reading in store.latest.values():
        if reading.sensor_id == device:
            return reading.sensor_id
    reading = store.latest.get(device)
    return reading.sensor_id if reading else None


@app.post("/api/control/{device}")
async def control(device: str, command: Command) -> dict:
    """Publish a command to a device's MQTT command topic.

    Fire-and-forget by design: this confirms the command was published, not
    that the device obeyed. Confirmation arrives on the normal telemetry path,
    which is what the UI reconciles against.
    """
    if not command.model_fields_set:
        raise HTTPException(
            status_code=400, detail="command must set at least one of 'on' or 'target'"
        )

    sensor_id = resolve_sensor_id(device)
    if sensor_id is None:
        raise HTTPException(
            status_code=404,
            detail=(
                f"unknown device '{device}'; no telemetry seen from it yet. "
                f"Known: {sorted(store.latest)}"
            ),
        )

    topic = COMMAND_TEMPLATE.format(sensor_id=sensor_id)
    # exclude_unset, not exclude_none: an explicit {"target": null} must survive
    # as a null so the device can clear its target and resume a free walk.
    payload = command.model_dump(exclude_unset=True)

    # Short-lived publisher: the ingest client lives inside the listener task,
    # and commands are rare enough that a connection per command is cheaper
    # than sharing state across tasks.
    try:
        async with aiomqtt.Client(
        hostname=MQTT_HOST,
        port=MQTT_PORT,
        username=MQTT_USERNAME,
        password=MQTT_PASSWORD,
        tls_params=aiomqtt.TLSParameters(cert_reqs=ssl.CERT_REQUIRED) if MQTT_TLS else None,
        identifier="pulsegrid-control",
        ) as client:
            await client.publish(topic, json.dumps(payload), qos=1)
    except aiomqtt.MqttError as exc:
        log.warning("command publish to %s failed: %s", topic, exc)
        raise HTTPException(status_code=502, detail=f"MQTT publish failed: {exc}") from exc
    except Exception as exc:
        log.exception("unexpected error publishing command to %s", topic)
        raise HTTPException(status_code=502, detail=f"MQTT publish failed: {exc}") from exc

    log.info("command published to %s: %s", topic, payload)
    return {"device": device, "sensor_id": sensor_id, "topic": topic, "command": payload}


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
        host=os.getenv("HOST", "0.0.0.0"),
        port=int(os.getenv("PORT", "8000")),
        loop="asyncio",
    )
