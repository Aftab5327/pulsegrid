# DigiSpace

A smart-building IoT dashboard: simulated sensors publish telemetry over MQTT,
a FastAPI service ingests it and fans it out over a WebSocket, and a React
dashboard renders it live.

```
┌──────────────┐   MQTT    ┌───────────┐   MQTT    ┌───────────┐  WebSocket  ┌───────────┐
│  simulated   │  publish  │ Mosquitto │ subscribe │  FastAPI  │    push     │   React   │
│  devices ×5  ├──────────►│  broker   ├──────────►│  backend  ├────────────►│ dashboard │
└──────────────┘  :1883    └───────────┘  :1883    └───────────┘   :8000     └───────────┘
   paho-mqtt                 Docker                  aiomqtt                    Vite
                                                   + in-memory                  :5173
                                                      store
```

Each hop is decoupled: the broker does not know about the backend, and the
backend does not know about the dashboard. Any of the three can restart without
taking the others down — the backend retries its broker connection, and the
dashboard reconnects its WebSocket.

## Layout

```
Project AVM Solutions/
├── backend/
│   ├── main.py                     FastAPI app: MQTT ingest, REST, WebSocket
│   ├── requirements.txt
│   ├── docker-compose.yml          Mosquitto broker
│   ├── mosquitto/config/
│   │   └── mosquitto.conf
│   └── simulators/
│       ├── devices.py              5 simulated sensors (paho-mqtt)
│       └── requirements.txt
└── frontend-dashboard/
    └── src/
        ├── App.tsx                 Shell, nav, connection status pill
        ├── hooks/useLiveData.ts    WebSocket client + shared live store
        ├── components/             The 5 metric cards
        └── store/                  Redux: card visibility only
```

## Running it

Four terminals, in this order. Each step assumes the previous one is up.

### 1. Broker

```powershell
cd backend
docker compose up -d
docker compose logs -f mosquitto   # optional
```

Listens on `1883` (MQTT) and `9001` (MQTT over WebSockets).

### 2. Backend

```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe main.py
```

Serves on `http://127.0.0.1:8000`.

> Use `python main.py`, not `uvicorn main:app`. On Windows the default event
> loop is the proactor loop, which has no `add_reader`/`add_writer`, and
> aiomqtt's transport needs them. The `__main__` block sets the selector policy
> before uvicorn builds its loop; doing it at import time is too late, because
> uvicorn imports the module from inside an already-running loop.

### 3. Sensors

```powershell
cd backend
.\.venv\Scripts\python.exe -m pip install -r simulators\requirements.txt
.\.venv\Scripts\python.exe simulators\devices.py
```

Publishes all five sensors every 2 seconds. Ctrl+C to stop.

### 4. Dashboard

```powershell
cd frontend-dashboard
npm install
npm run dev
```

Open http://localhost:5173. The header shows **LIVE** in teal once the
WebSocket is connected, **offline** in grey when it is not.

### Check it is working

```powershell
curl http://127.0.0.1:8000/            # health + metrics seen so far
curl http://127.0.0.1:8000/api/latest  # newest reading per metric
```

## Telemetry format

### Device → broker

Sensors publish JSON to `digispace/sensors/<sensor_id>/telemetry`, and the
backend subscribes to the wildcard `digispace/sensors/+/telemetry`.

```json
{
  "sensor_id": "carbon-01",
  "metric": "carbon",
  "value": 96.7,
  "unit": "gCO2/kWh",
  "site": "building-1",
  "ts": "2026-08-06T12:39:01.632363Z"
}
```

| Field | Type | Notes |
| --- | --- | --- |
| `sensor_id` | string | Unique per device, e.g. `lights-01` |
| `metric` | string | One of `lights`, `water`, `carbon`, `energy`, `footfall` |
| `value` | number | The reading |
| `unit` | string | Unit of `value` |
| `site` | string | Building identifier |
| `ts` | string | ISO 8601, UTC, `Z`-suffixed |

The five sensors:

| Sensor | Metric | Unit | Range |
| --- | --- | --- | --- |
| `lights-01` | lights | `k` | 2700 – 5000 |
| `water-01` | water | `m3` | 5 – 12 |
| `carbon-01` | carbon | `gCO2/kWh` | 70 – 140 |
| `energy-01` | energy | `kWh` | 2000 – 6000 |
| `footfall-01` | footfall | `people` | 40 – 160 |

Each walks its value with a bounded random walk — Gaussian steps at 2% of its
own range, reflecting off the bounds — so the traces look plausible rather than
jumping randomly.

Payloads are validated with Pydantic on arrival. Anything malformed is logged
and dropped, so one bad sensor cannot take the ingest loop down.

### Backend → dashboard

WebSocket at `ws://localhost:8000/ws`. The dashboard is receive-only.

On connect, one snapshot of the latest reading per metric:

```json
{
  "type": "snapshot",
  "data": {
    "lights": { "sensor_id": "lights-01", "metric": "lights", "value": 4389, "unit": "k", "site": "building-1", "ts": "..." },
    "water":  { "...": "..." }
  }
}
```

Then one frame per reading as it arrives:

```json
{ "type": "reading", "data": { "sensor_id": "footfall-01", "metric": "footfall", "value": 113, "unit": "people", "site": "building-1", "ts": "..." } }
```

And a frame whenever the backend's own broker link changes state:

```json
{ "type": "broker", "connected": false }
```

### REST

| Endpoint | Returns |
| --- | --- |
| `GET /` | Health, configured broker and topic, metrics seen, history size |
| `GET /api/latest` | Newest reading for every metric |
| `GET /api/history/{metric}` | Up to the last 120 readings, oldest first; 404 for an unknown metric |

The dashboard uses `/api/history/{metric}` to backfill its charts on load, so a
freshly opened page shows a trend immediately rather than drawing one point
every two seconds.

## State and persistence

Everything is in memory. The backend keeps the latest reading per metric plus a
`deque(maxlen=120)` of recent readings — roughly four minutes at the default
2-second cadence. **Restarting the backend discards all history.** Swap the
store in `main.py` for a time-series database if you need it to survive.

## Configuration

Backend, via environment (see `backend/.env.example`):

| Variable | Default |
| --- | --- |
| `MQTT_HOST` | `localhost` |
| `MQTT_PORT` | `1883` |
| `MQTT_TOPIC` | `digispace/sensors/+/telemetry` |
| `HISTORY_SIZE` | `120` |
| `CORS_ORIGINS` | `http://localhost:5173` |

Simulator: `MQTT_HOST`, `MQTT_PORT`, `PUBLISH_INTERVAL`, `SITE`, `MQTT_QOS`.

Frontend, via `.env.local` (see `frontend-dashboard/.env.example`):
`VITE_WS_URL`, `VITE_API_URL`.

## Security

The development broker allows anonymous connections over plaintext MQTT. That
is acceptable bound to localhost and nowhere else. Before this runs anywhere
shared, switch to TLS and username/password — the steps are written out at the
top of `backend/mosquitto/config/mosquitto.conf`.
