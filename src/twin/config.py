"""Pydantic configuration for the serial production line twin.

Stations and buffers are addressed with 1-based station ids. ``buffer_after``
on station ``i`` is the capacity of the buffer between station ``i`` and
station ``i + 1``; the last station has no downstream buffer.
"""

from __future__ import annotations

import math

from pydantic import BaseModel, Field, model_validator

SHIFT_SECONDS = 8 * 3600


class StationConfig(BaseModel):
    """Parameters of a single station (all times in seconds)."""

    cycle_time_mean: float = Field(gt=0)
    cycle_time_cv: float = Field(ge=0, default=0.25)
    mtbf: float | None = Field(default=None, gt=0, description="Mean operating time between failures; None = never fails")
    mttr: float = Field(default=0.0, ge=0)
    buffer_after: int | None = Field(default=None, ge=1, description="Capacity of the buffer after this station")

    @property
    def availability(self) -> float:
        """Steady-state availability implied by MTBF and MTTR."""
        if self.mtbf is None:
            return 1.0
        return self.mtbf / (self.mtbf + self.mttr)

    @property
    def effective_cycle_time(self) -> float:
        """Mean cycle time inflated by downtime (inverse of effective capacity)."""
        return self.cycle_time_mean / self.availability


class LineConfig(BaseModel):
    """A serial line of stations separated by finite buffers."""

    stations: list[StationConfig] = Field(min_length=2)
    shift_seconds: float = Field(default=SHIFT_SECONDS, gt=0)

    @model_validator(mode="after")
    def _check_buffers(self) -> "LineConfig":
        for i, st in enumerate(self.stations[:-1]):
            if st.buffer_after is None:
                raise ValueError(f"station {i + 1} needs buffer_after")
        if self.stations[-1].buffer_after is not None:
            raise ValueError("last station must not define buffer_after")
        return self

    @property
    def n_stations(self) -> int:
        """Number of stations on the line."""
        return len(self.stations)

    def station(self, station_id: int) -> StationConfig:
        """Return the config of station ``station_id`` (1-based)."""
        if not 1 <= station_id <= self.n_stations:
            raise ValueError(f"station {station_id} out of range 1..{self.n_stations}")
        return self.stations[station_id - 1]

    def analytic_bottleneck(self) -> int:
        """Station id with the lowest effective capacity (ignores buffering effects)."""
        return max(range(1, self.n_stations + 1), key=lambda i: self.station(i).effective_cycle_time)

    def capacity_bound_per_shift(self) -> float:
        """Upper bound on units/shift from the slowest effective station."""
        slowest = max(s.effective_cycle_time for s in self.stations)
        return self.shift_seconds / slowest


def lognormal_params(mean: float, cv: float) -> tuple[float, float]:
    """Return (mu, sigma) of a lognormal with the given mean and coefficient of variation."""
    sigma2 = math.log(1.0 + cv * cv)
    return math.log(mean) - sigma2 / 2.0, math.sqrt(sigma2)
