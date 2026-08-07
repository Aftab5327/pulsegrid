"""Simulated IoT sensors publishing JSON telemetry over MQTT.

Five sensors, one per dashboard metric, each walking its own value within a
fixed range and publishing to:

    digispace/sensors/<sensor_id>/telemetry

Configuration (all optional, via environment):

    MQTT_HOST           broker hostname          default localhost
    MQTT_PORT           broker port              default 1883
    PUBLISH_INTERVAL    seconds between rounds   default 2.0
    SITE                site id in the payload   default building-1
    MQTT_QOS            0, 1 or 2                default 1

Run:

    python simulators/devices.py
"""

from __future__ import annotations

import json
import os
import random
import signal
import sys
import time
from dataclasses import dataclass
from datetime import datetime, timezone

import paho.mqtt.client as mqtt

# --- configuration -----------------------------------------------------------

MQTT_HOST = os.getenv("MQTT_HOST", "localhost")
MQTT_PORT = int(os.getenv("MQTT_PORT", "1883"))
PUBLISH_INTERVAL = float(os.getenv("PUBLISH_INTERVAL", "2.0"))
SITE = os.getenv("SITE", "building-1")
MQTT_QOS = int(os.getenv("MQTT_QOS", "1"))

TOPIC_TEMPLATE = "digispace/sensors/{sensor_id}/telemetry"


# --- sensors -----------------------------------------------------------------


@dataclass
class Sensor:
    """One sensor performing a bounded random walk.

    The walk steps by a fraction of its own range rather than a fixed amount,
    so every sensor moves at a comparable pace relative to its scale. Steps are
    Gaussian and reflect off the bounds instead of clamping — clamping makes a
    value stick to the limit once it gets there, which reads as a dead sensor.
    """

    sensor_id: str
    metric: str
    unit: str
    low: float
    high: float
    value: float
    precision: int = 1
    volatility: float = 0.02

    @property
    def _step(self) -> float:
        return (self.high - self.low) * self.volatility

    def next_value(self) -> float:
        self.value += random.gauss(0, self._step)

        # Reflect back inside the range, then clamp in case a large step
        # overshot the far bound on the way back.
        if self.value < self.low:
            self.value = self.low + (self.low - self.value)
        elif self.value > self.high:
            self.value = self.high - (self.value - self.high)
        self.value = max(self.low, min(self.high, self.value))

        return round(self.value, self.precision)

    def payload(self, site: str) -> dict:
        return {
            "sensor_id": self.sensor_id,
            "metric": self.metric,
            "value": self.next_value(),
            "unit": self.unit,
            "site": site,
            "ts": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        }


def build_sensors() -> list[Sensor]:
    """Start each sensor mid-range so nothing opens pinned to a bound."""
    return [
        Sensor("lights-01", "lights", "k", 2700, 5000, 4300, precision=0),
        Sensor("water-01", "water", "m3", 5, 12, 8.4, precision=2),
        Sensor("carbon-01", "carbon", "gCO2/kWh", 70, 140, 95, precision=1),
        Sensor("energy-01", "energy", "kWh", 2000, 6000, 3800, precision=0),
        Sensor("footfall-01", "footfall", "people", 40, 160, 120, precision=0),
    ]


# --- runner ------------------------------------------------------------------


class Simulator:
    def __init__(self) -> None:
        self.sensors = build_sensors()
        self.running = True
        self.client = mqtt.Client(
            mqtt.CallbackAPIVersion.VERSION2,
            client_id=f"digispace-simulator-{os.getpid()}",
        )
        self.client.on_connect = self._on_connect
        self.client.on_disconnect = self._on_disconnect
        # Cap the backoff so a broker restart is picked up promptly.
        self.client.reconnect_delay_set(min_delay=1, max_delay=10)

    def _on_connect(self, _client, _userdata, _flags, reason_code, _properties=None):
        if reason_code == 0:
            print(f"connected to {MQTT_HOST}:{MQTT_PORT}", flush=True)
        else:
            print(f"connect failed: {reason_code}", file=sys.stderr, flush=True)

    def _on_disconnect(self, _client, _userdata, _flags, reason_code, _properties=None):
        if self.running and reason_code != 0:
            print(f"disconnected ({reason_code}); paho will retry", file=sys.stderr, flush=True)

    def stop(self, *_args) -> None:
        self.running = False

    def connect(self) -> None:
        """Block until the first connection succeeds, so a broker that is not
        up yet is a delay rather than a crash."""
        while self.running:
            try:
                self.client.connect(MQTT_HOST, MQTT_PORT, keepalive=60)
                return
            except OSError as exc:
                print(f"broker unavailable ({exc}); retrying in 3s", file=sys.stderr, flush=True)
                # Interruptible sleep, so Ctrl+C works while we are waiting.
                for _ in range(30):
                    if not self.running:
                        return
                    time.sleep(0.1)

    def run(self) -> None:
        signal.signal(signal.SIGINT, self.stop)
        signal.signal(signal.SIGTERM, self.stop)

        self.connect()
        if not self.running:
            return

        self.client.loop_start()
        print(
            f"publishing {len(self.sensors)} sensors every {PUBLISH_INTERVAL}s "
            f"to digispace/sensors/<sensor_id>/telemetry",
            flush=True,
        )

        try:
            while self.running:
                started = time.monotonic()

                for sensor in self.sensors:
                    payload = sensor.payload(SITE)
                    topic = TOPIC_TEMPLATE.format(sensor_id=sensor.sensor_id)
                    info = self.client.publish(topic, json.dumps(payload), qos=MQTT_QOS)
                    if info.rc != mqtt.MQTT_ERR_SUCCESS:
                        print(f"publish to {topic} failed: {info.rc}", file=sys.stderr, flush=True)
                    else:
                        print(f"{topic} -> {payload['value']} {payload['unit']}", flush=True)

                # Sleep in slices so Ctrl+C is picked up without waiting out a
                # whole interval; subtract the work we just did so the cadence
                # stays honest.
                remaining = PUBLISH_INTERVAL - (time.monotonic() - started)
                while self.running and remaining > 0:
                    time.sleep(min(0.1, remaining))
                    remaining -= 0.1
        finally:
            print("\nstopping simulator", flush=True)
            self.client.loop_stop()
            self.client.disconnect()


if __name__ == "__main__":
    Simulator().run()
