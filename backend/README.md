# DigiSpace Backend

Telemetry backend for the DigiSpace dashboard.

```
simulated devices --MQTT--> Mosquitto --MQTT--> FastAPI --WebSocket--> dashboard
```

## Run it

Four terminals, in this order.

**1. Broker**

```powershell
docker compose up -d
```

**2. Backend**

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe run.py
```

Use `run.py`, not `uvicorn app.main:app`. On Windows the default event loop is
the proactor loop, which lacks `add_reader`/`add_writer`; aiomqtt needs them.
`run.py` sets the selector policy before uvicorn builds its loop — setting it
inside `app/main.py` is too late, because uvicorn imports the app from inside
the already-running loop.

**3. Simulator**

```powershell
.\.venv\Scripts\python.exe -m simulator.simulate_devices
```

**4. Dashboard**

```powershell
cd ..\frontend-dashboard
npm run dev
```

## Topics

Devices publish JSON to `digispace/<site>/<metric>/state`, and the backend
subscribes to `digispace/building-1/+/state`.

| Topic | Payload |
| --- | --- |
| `digispace/building-1/lights/state` | `{"kelvin": 4300, "on": true}` |
| `digispace/building-1/water/state` | `{"cubic_meters": 8.42}` |
| `digispace/building-1/carbon/state` | `{"g_co2_per_kwh": 95, "mix": {"Coal": 30, ...}}` |
| `digispace/building-1/energy/state` | `{"kwh": 60}` |
| `digispace/building-1/footfall/state` | `{"count": 120}` |

Payloads are validated with Pydantic on arrival. Anything malformed is logged
and dropped — one bad device cannot take the dashboard down.

## WebSocket

`ws://localhost:8000/ws/telemetry`. The dashboard is receive-only.

```jsonc
// on connect — every card at once
{"type": "snapshot", "data": {"lights": {...}, "water": {...}, ...}}

// thereafter — one card at a time, as devices report
{"type": "update", "metric": "footfall", "data": {"labels": [...], "series": [...], "current": 78}}

// backend's own link to the broker went up or down
{"type": "broker", "connected": false}
```

Card payloads are shaped to match the existing dashboard cards one-for-one, so
the frontend does no reshaping. See `app/schemas.py`.

## HTTP

- `GET /api/health` — status plus which broker and topic are configured
- `GET /api/snapshot` — same payload as the WebSocket snapshot frame

## History

`SeriesCard` (energy, footfall) carries a 7-day window. It is held in memory
only: on startup the six past days are seeded pseudo-randomly and the last slot
("Today") is driven live by MQTT. The window shifts when the wall clock crosses
midnight. **Restarting the backend reseeds the history** — swap `app/state.py`
for a real store if you need it to survive restarts.

## Config

Environment variables, see `.env.example`:
`MQTT_HOST`, `MQTT_PORT`, `MQTT_TOPIC_PREFIX`, `SITE_ID`, `CORS_ORIGINS`.

The bundled `mosquitto.conf` allows anonymous access. That is fine bound to
localhost; add a `password_file` before exposing port 1883 anywhere else.

## Tests

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
.\.venv\Scripts\python.exe -m pytest
```

`tests/test_pipeline.py` drives `_handle` — the exact function the MQTT
subscriber calls per message — so it covers ingest, validation, the store, and
the WebSocket without needing a running broker.
