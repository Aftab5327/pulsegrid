"""Simulated smart-building devices publishing to MQTT.

Each metric is an independent async task with its own cadence and its own
random-walk model, so the dashboard sees uncorrelated, plausibly-shaped data
rather than five values ticking in lockstep.

    python -m simulator.simulate_devices
    python -m simulator.simulate_devices --host localhost --port 1883
"""

import argparse
import asyncio
import json
import logging
import random
import sys
from datetime import datetime

import aiomqtt

if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
log = logging.getLogger("simulator")


def _clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def _occupancy_factor(now: datetime) -> float:
    """Rough office curve: quiet overnight, peaks late morning and mid afternoon."""
    hour = now.hour + now.minute / 60
    if hour < 6 or hour > 22:
        return 0.12
    return 0.25 + 0.75 * max(0.0, 1 - abs(hour - 13) / 7)


class Device:
    metric: str = ""
    interval: float = 5.0

    async def run(self, client: aiomqtt.Client, prefix: str, site: str) -> None:
        topic = f"{prefix}/{site}/{self.metric}/state"
        while True:
            payload = self.next_reading()
            await client.publish(topic, json.dumps(payload), qos=1)
            log.info("%s -> %s", topic, payload)
            await asyncio.sleep(self.interval)

    def next_reading(self) -> dict:
        raise NotImplementedError


class LightsDevice(Device):
    """Colour temperature drifts warm in the evening, cool at midday."""

    metric = "lights"
    interval = 4.0

    def __init__(self) -> None:
        self.kelvin = 4300.0

    def next_reading(self) -> dict:
        now = datetime.now()
        target = 2700 + 2300 * _occupancy_factor(now)
        self.kelvin = _clamp(self.kelvin + (target - self.kelvin) * 0.2 + random.uniform(-60, 60), 2700, 5000)
        return {"kelvin": round(self.kelvin), "on": 6 <= now.hour <= 22}


class WaterDevice(Device):
    """Cumulative consumption for the day, resetting at midnight."""

    metric = "water"
    interval = 6.0

    def __init__(self) -> None:
        self.total = 8.42
        self.day = datetime.now().day

    def next_reading(self) -> dict:
        now = datetime.now()
        if now.day != self.day:
            self.total = 0.0
            self.day = now.day
        self.total += random.uniform(0.005, 0.05) * _occupancy_factor(now)
        return {"cubic_meters": round(self.total, 2)}


class CarbonDevice(Device):
    """Grid intensity follows the generation mix; renewables push it down."""

    metric = "carbon"
    interval = 10.0

    def __init__(self) -> None:
        self.mix = {"Coal": 30.0, "Hydro": 20.0, "Nuclear": 20.0, "Wind": 15.0, "Solar": 15.0}

    def next_reading(self) -> dict:
        now = datetime.now()
        drifted = {k: max(2.0, v + random.uniform(-2, 2)) for k, v in self.mix.items()}
        # Solar tracks daylight before the mix is renormalised to 100%.
        drifted["Solar"] = max(1.0, 25 * max(0.0, 1 - abs(now.hour - 13) / 6))
        total = sum(drifted.values())
        self.mix = {k: round(v * 100 / total, 1) for k, v in drifted.items()}

        renewable = self.mix["Hydro"] + self.mix["Wind"] + self.mix["Solar"]
        intensity = 40 + (100 - renewable) * 1.6 + random.uniform(-5, 5)
        return {"g_co2_per_kwh": round(_clamp(intensity, 20, 400), 1), "mix": self.mix}


class EnergyDevice(Device):
    """kWh accumulated so far today."""

    metric = "energy"
    interval = 5.0

    def __init__(self) -> None:
        self.kwh = 60.0
        self.day = datetime.now().day

    def next_reading(self) -> dict:
        now = datetime.now()
        if now.day != self.day:
            self.kwh = 0.0
            self.day = now.day
        self.kwh += random.uniform(0.2, 1.6) * _occupancy_factor(now)
        return {"kwh": round(self.kwh, 1)}


class FootfallDevice(Device):
    """People currently inside; entries and exits track the occupancy curve."""

    metric = "footfall"
    interval = 3.0

    def __init__(self) -> None:
        self.count = 120

    def next_reading(self) -> dict:
        factor = _occupancy_factor(datetime.now())
        target = 160 * factor
        self.count = int(_clamp(self.count + (target - self.count) * 0.25 + random.uniform(-6, 6), 0, 250))
        return {"count": self.count}


async def main() -> None:
    parser = argparse.ArgumentParser(description="DigiSpace device simulator")
    parser.add_argument("--host", default="localhost")
    parser.add_argument("--port", type=int, default=1883)
    parser.add_argument("--prefix", default="digispace")
    parser.add_argument("--site", default="building-1")
    args = parser.parse_args()

    devices = [LightsDevice(), WaterDevice(), CarbonDevice(), EnergyDevice(), FootfallDevice()]

    while True:
        try:
            async with aiomqtt.Client(hostname=args.host, port=args.port) as client:
                log.info("connected to %s:%d, publishing under %s/%s", args.host, args.port, args.prefix, args.site)
                async with asyncio.TaskGroup() as group:
                    for device in devices:
                        group.create_task(device.run(client, args.prefix, args.site))
        except* aiomqtt.MqttError as exc:
            log.warning("broker unavailable (%s); retrying in 5s", exc.exceptions[0])
            await asyncio.sleep(5)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        log.info("simulator stopped")
