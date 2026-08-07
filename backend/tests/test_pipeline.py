"""Covers ingest -> store -> WebSocket without needing a live broker.

`_handle` is the exact function the MQTT subscriber calls per message, so
feeding it raw topic/payload pairs exercises everything but the TCP hop.
"""

import asyncio
import json

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.mqtt_client import _handle
from app.state import store

TOPIC = "digispace/building-1/{}/state"


def send(metric: str, payload: dict) -> None:
    asyncio.run(_handle(TOPIC.format(metric), json.dumps(payload).encode()))


def test_readings_land_in_snapshot():
    send("lights", {"kelvin": 4300, "on": True})
    send("water", {"cubic_meters": 8.42})
    send("carbon", {"g_co2_per_kwh": 95, "mix": {"Coal": 30, "Hydro": 20, "Nuclear": 20, "Wind": 15, "Solar": 15}})
    send("energy", {"kwh": 60})
    send("footfall", {"count": 120})

    snap = store.snapshot()
    assert snap.lights.value == 4300
    assert snap.lights.on is True
    assert snap.water.value == 8.42
    assert snap.carbon.intensity == 95
    assert [slice_.name for slice_ in snap.carbon.mix] == ["Coal", "Hydro", "Nuclear", "Wind", "Solar"]
    assert snap.energy.current == 60
    assert snap.footfall.current == 120


def test_series_cards_keep_a_seven_day_window():
    send("energy", {"kwh": 77})
    card = store.snapshot().energy
    assert len(card.series) == 7
    assert len(card.labels) == 7
    assert card.labels[-1] == "Today"
    assert card.series[-1] == 77  # live slot is the last one


def test_malformed_payloads_are_dropped_not_fatal():
    send("lights", {"kelvin": 4300, "on": True})
    before = store.snapshot().lights.value

    send("lights", {"kelvin": 99999})  # out of the 2700-5000 range
    send("lights", {"nope": 1})  # missing required field
    asyncio.run(_handle(TOPIC.format("lights"), b"not json"))
    asyncio.run(_handle("digispace/building-1/unknown/state", b"{}"))

    assert store.snapshot().lights.value == before


def test_websocket_receives_snapshot_on_connect():
    send("footfall", {"count": 42})
    with TestClient(app) as client:
        with client.websocket_connect("/ws/telemetry") as ws:
            message = ws.receive_json()
    assert message["type"] == "snapshot"
    assert message["data"]["footfall"]["current"] == 42
    assert set(message["data"]) == {"lights", "water", "carbon", "energy", "footfall"}


def test_snapshot_endpoint_matches_websocket_payload():
    with TestClient(app) as client:
        assert client.get("/api/health").json()["status"] == "ok"
        body = client.get("/api/snapshot").json()
    assert set(body) == {"lights", "water", "carbon", "energy", "footfall"}


@pytest.mark.asyncio
async def test_updates_are_broadcast_to_connected_clients():
    from app.hub import hub

    received = []

    class FakeSocket:
        async def send_json(self, message):
            received.append(message)

    socket = FakeSocket()
    await hub.add(socket)
    try:
        await _handle(TOPIC.format("footfall"), b'{"count": 7}')
    finally:
        await hub.discard(socket)

    assert received[-1]["type"] == "update"
    assert received[-1]["metric"] == "footfall"
    assert received[-1]["data"]["current"] == 7
