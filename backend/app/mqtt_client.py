"""MQTT ingest: subscribe to device telemetry, update the store, fan out.

Runs as a single long-lived asyncio task owned by the FastAPI lifespan. If the
broker goes away the task reconnects with a fixed backoff rather than dying,
so the dashboard keeps its last-known values instead of going blank.
"""

import asyncio
import json
import logging

import aiomqtt
from pydantic import ValidationError

from .config import MQTT_HOST, MQTT_PORT, TELEMETRY_WILDCARD
from .hub import hub
from .schemas import READING_MODELS
from .state import store

log = logging.getLogger(__name__)

RECONNECT_SECONDS = 5

# metric id -> (store method, name used on the wire)
_APPLIERS = {
    "lights": store.apply_lights,
    "water": store.apply_water,
    "carbon": store.apply_carbon,
    "energy": store.apply_energy,
    "footfall": store.apply_footfall,
}


def _metric_from_topic(topic: str) -> str | None:
    # digispace/building-1/<metric>/state
    parts = topic.split("/")
    if len(parts) == 4 and parts[3] == "state":
        return parts[2]
    return None


async def _handle(topic: str, raw: bytes) -> None:
    metric = _metric_from_topic(topic)
    if metric is None or metric not in READING_MODELS:
        log.warning("ignoring unknown topic %s", topic)
        return

    try:
        reading = READING_MODELS[metric].model_validate_json(raw)
    except ValidationError as exc:
        log.warning("bad payload on %s: %s", topic, exc.errors()[:2])
        return
    except json.JSONDecodeError:
        log.warning("non-JSON payload on %s", topic)
        return

    card = _APPLIERS[metric](reading)
    await hub.broadcast({"type": "update", "metric": metric, "data": card.model_dump()})


async def run_mqtt_ingest() -> None:
    while True:
        try:
            async with aiomqtt.Client(hostname=MQTT_HOST, port=MQTT_PORT) as client:
                await client.subscribe(TELEMETRY_WILDCARD)
                log.info("subscribed to %s on %s:%d", TELEMETRY_WILDCARD, MQTT_HOST, MQTT_PORT)
                await hub.broadcast({"type": "broker", "connected": True})
                async for message in client.messages:
                    await _handle(str(message.topic), message.payload)
        except asyncio.CancelledError:
            raise
        except aiomqtt.MqttError as exc:
            log.warning("MQTT connection lost (%s); retrying in %ds", exc, RECONNECT_SECONDS)
            await hub.broadcast({"type": "broker", "connected": False})
            await asyncio.sleep(RECONNECT_SECONDS)
