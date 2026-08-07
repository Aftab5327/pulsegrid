"""Wire format shared by MQTT ingest and the dashboard WebSocket.

Device payloads (what the simulator publishes) are the `*Reading` models.
Card payloads (what the dashboard consumes) are the `*Card` models — they are
shaped to match the existing DigiSpace cards one-for-one so the frontend does
no reshaping of its own.
"""

from typing import Literal

from pydantic import BaseModel, Field

MetricId = Literal["lights", "water", "carbon", "energy", "footfall"]


# --- device -> backend -------------------------------------------------------


class LightsReading(BaseModel):
    kelvin: float = Field(ge=2700, le=5000)
    on: bool = True


class WaterReading(BaseModel):
    cubic_meters: float = Field(ge=0)


class CarbonReading(BaseModel):
    g_co2_per_kwh: float = Field(ge=0)
    mix: dict[str, float]


class EnergyReading(BaseModel):
    kwh: float = Field(ge=0)


class FootfallReading(BaseModel):
    count: int = Field(ge=0)


READING_MODELS: dict[str, type[BaseModel]] = {
    "lights": LightsReading,
    "water": WaterReading,
    "carbon": CarbonReading,
    "energy": EnergyReading,
    "footfall": FootfallReading,
}


# --- backend -> dashboard ----------------------------------------------------


class LightsCard(BaseModel):
    value: float
    min: float = 2700
    max: float = 5000
    on: bool


class WaterCard(BaseModel):
    value: float
    unit: str = "m3"
    delta: float  # negative means less water used than the comparison day
    comparison_label: str


class MixSlice(BaseModel):
    name: str
    value: float


class CarbonCard(BaseModel):
    intensity: float
    unit: str = "CO2/kWh"
    mix: list[MixSlice]


class SeriesCard(BaseModel):
    labels: list[str]
    series: list[float]
    current: float


class Snapshot(BaseModel):
    lights: LightsCard | None = None
    water: WaterCard | None = None
    carbon: CarbonCard | None = None
    energy: SeriesCard | None = None
    footfall: SeriesCard | None = None
