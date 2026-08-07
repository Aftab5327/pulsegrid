"""In-memory telemetry store.

Holds the latest value for each metric plus a rolling `HISTORY_DAYS` window for
the two series cards. Nothing is persisted: on restart the history is reseeded
and the live slot starts over. That is deliberate — see README.
"""

import random
from datetime import date, timedelta

from .config import HISTORY_DAYS
from .schemas import (
    CarbonCard,
    CarbonReading,
    EnergyReading,
    FootfallReading,
    LightsCard,
    LightsReading,
    MixSlice,
    SeriesCard,
    Snapshot,
    WaterCard,
    WaterReading,
)

_WEEKDAY_INITIALS = ["M", "T", "W", "T", "F", "S", "S"]


def _labels(today: date) -> list[str]:
    """Weekday initials for the trailing window, with the live slot last."""
    days = [today - timedelta(days=offset) for offset in range(HISTORY_DAYS - 1, 0, -1)]
    return [_WEEKDAY_INITIALS[day.weekday()] for day in days] + ["Today"]


class TelemetryStore:
    def __init__(self, seed: int = 7) -> None:
        self._rng = random.Random(seed)
        self._today = date.today()

        self.lights: LightsCard | None = None
        self.water: WaterCard | None = None
        self.carbon: CarbonCard | None = None

        # index -1 is the live "Today" slot, filled by incoming readings
        self._energy_history: list[float] = self._seed(40, 130)
        self._footfall_history: list[float] = self._seed(70, 140)
        self._water_yesterday: float | None = None

    def _seed(self, low: float, high: float) -> list[float]:
        past = [round(self._rng.uniform(low, high)) for _ in range(HISTORY_DAYS - 1)]
        return past + [0.0]

    def _roll_if_new_day(self) -> None:
        """Shift the window forward when the wall clock crosses midnight."""
        today = date.today()
        if today == self._today:
            return
        elapsed = min((today - self._today).days, HISTORY_DAYS)
        for history in (self._energy_history, self._footfall_history):
            for _ in range(elapsed):
                history.pop(0)
                history.append(0.0)
        self._today = today

    # --- ingest --------------------------------------------------------------

    def apply_lights(self, reading: LightsReading) -> LightsCard:
        self.lights = LightsCard(value=reading.kelvin, on=reading.on)
        return self.lights

    def apply_water(self, reading: WaterReading) -> WaterCard:
        # First reading of a run establishes the comparison baseline.
        if self._water_yesterday is None:
            self._water_yesterday = round(reading.cubic_meters * self._rng.uniform(0.9, 1.2), 2)
        self.water = WaterCard(
            value=round(reading.cubic_meters, 2),
            delta=round(reading.cubic_meters - self._water_yesterday, 2),
            comparison_label="yesterday",
        )
        return self.water

    def apply_carbon(self, reading: CarbonReading) -> CarbonCard:
        self.carbon = CarbonCard(
            intensity=round(reading.g_co2_per_kwh),
            mix=[MixSlice(name=name, value=value) for name, value in reading.mix.items()],
        )
        return self.carbon

    def apply_energy(self, reading: EnergyReading) -> SeriesCard:
        self._roll_if_new_day()
        self._energy_history[-1] = round(reading.kwh, 1)
        return self.energy_card()

    def apply_footfall(self, reading: FootfallReading) -> SeriesCard:
        self._roll_if_new_day()
        self._footfall_history[-1] = reading.count
        return self.footfall_card()

    # --- read ----------------------------------------------------------------

    def energy_card(self) -> SeriesCard:
        return SeriesCard(
            labels=_labels(self._today),
            series=list(self._energy_history),
            current=self._energy_history[-1],
        )

    def footfall_card(self) -> SeriesCard:
        return SeriesCard(
            labels=_labels(self._today),
            series=list(self._footfall_history),
            current=self._footfall_history[-1],
        )

    def snapshot(self) -> Snapshot:
        return Snapshot(
            lights=self.lights,
            water=self.water,
            carbon=self.carbon,
            energy=self.energy_card(),
            footfall=self.footfall_card(),
        )


store = TelemetryStore()
