"""SimPy discrete-event model of a serial production line with finite buffers.

Modelling choices (see docs/ASSUMPTIONS.md): infinite raw material upstream of
station 1, unbounded sink after the last station, blocking-after-service,
failures counted in operating time (a station cannot fail while starved or
blocked), and independent seeded random streams per station so replications
that differ only in configuration share common random numbers.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Iterator

import numpy as np
import simpy

from src.twin.config import LineConfig, lognormal_params

STATES = ("busy", "starved", "blocked", "down")
SNAPSHOT_INTERVAL = 60.0
MIN_LOGGED_WAIT = 1.0


@dataclass
class Part:
    """A unit of work flowing through the line."""

    part_id: int
    t_in: float


class Station:
    """One workstation: pulls from the upstream buffer, processes, pushes downstream."""

    def __init__(self, line: "ProductionLine", index: int, rng_cycle: np.random.Generator, rng_fail: np.random.Generator) -> None:
        self.line = line
        self.index = index
        self.sid = index + 1
        self.cfg = line.config.stations[index]
        self.rng_cycle = rng_cycle
        self.rng_fail = rng_fail
        self.mu, self.sigma = lognormal_params(self.cfg.cycle_time_mean, max(self.cfg.cycle_time_cv, 1e-9))
        self.time_in = {s: 0.0 for s in STATES}
        self.state = "busy"
        self._since = 0.0
        self.completed = 0
        self.breakdowns = 0
        self.op_left = self._draw_uptime()

    def _draw_uptime(self) -> float:
        return float(self.rng_fail.exponential(self.cfg.mtbf)) if self.cfg.mtbf else float("inf")

    def _draw_repair(self) -> float:
        return float(self.rng_fail.exponential(self.cfg.mttr)) if self.cfg.mttr > 0 else 0.0

    def set_state(self, new: str) -> None:
        """Credit elapsed time to the current state and switch to ``new``."""
        now = self.line.env.now
        self.time_in[self.state] += now - self._since
        self._since = now
        self.state = new

    def _cycle_time(self) -> float:
        return float(self.rng_cycle.lognormal(self.mu, self.sigma))

    def _process(self) -> Iterator[simpy.Event]:
        env = self.line.env
        remaining = self._cycle_time()
        self.set_state("busy")
        while remaining > 0:
            if self.op_left <= remaining:
                yield env.timeout(self.op_left)
                remaining -= self.op_left
                repair = self._draw_repair()
                self.set_state("down")
                self.line.log("breakdown_start", self.sid, expected_repair=round(repair, 2))
                yield env.timeout(repair)
                self.breakdowns += 1
                self.line.log("breakdown_end", self.sid, duration=round(repair, 2))
                self.set_state("busy")
                self.op_left = self._draw_uptime()
            else:
                yield env.timeout(remaining)
                self.op_left -= remaining
                remaining = 0.0

    def _wait(self, kind: str, t0: float) -> None:
        duration = self.line.env.now - t0
        if duration >= MIN_LOGGED_WAIT:
            self.line.log(f"{kind}_end", self.sid, duration=round(duration, 2))

    def run(self) -> Iterator[simpy.Event]:
        """Main station loop."""
        line, env = self.line, self.line.env
        last = self.index == line.config.n_stations - 1
        while True:
            if self.index == 0:
                part = line.new_part()
            else:
                self.set_state("starved")
                t0 = env.now
                part = yield line.buffers[self.index - 1].get()
                self._wait("starved", t0)
            yield from self._process()
            self.completed += 1
            if last:
                line.exit_part(part)
            else:
                self.set_state("blocked")
                t0 = env.now
                yield line.buffers[self.index].put(part)
                self._wait("blocked", t0)


@dataclass
class RunResult:
    """Outcome of one simulated run."""

    seed: int
    duration: float
    throughput_per_shift: float
    kpis: dict[str, Any]
    rolling: list[dict[str, Any]]
    events: list[dict[str, Any]] = field(repr=False)


class ProductionLine:
    """The digital twin: build from a :class:`LineConfig`, run with a seed."""

    def __init__(self, config: LineConfig, seed: int = 0) -> None:
        self.config = config
        self.seed = seed
        self.env = simpy.Environment()
        self.events: list[dict[str, Any]] = []
        self.snapshots: list[dict[str, Any]] = []
        self.exited = 0
        self.wip = 0
        self.wip_area = 0.0
        self._wip_t = 0.0
        self.sojourns: list[float] = []
        self._next_part = 0
        self.buffers = [simpy.Store(self.env, capacity=s.buffer_after) for s in config.stations[:-1]]
        seqs = np.random.SeedSequence(seed).spawn(2 * config.n_stations)
        self.stations = [
            Station(self, i, np.random.default_rng(seqs[2 * i]), np.random.default_rng(seqs[2 * i + 1]))
            for i in range(config.n_stations)
        ]
        for st in self.stations:
            self.env.process(st.run())
        self.env.process(self._sampler())

    def log(self, event: str, station: int, **data: Any) -> None:
        """Append a structured event to the event log."""
        self.events.append({"t": round(self.env.now, 2), "event": event, "station": station, **data})

    def _update_wip(self, delta: int) -> None:
        now = self.env.now
        self.wip_area += self.wip * (now - self._wip_t)
        self._wip_t = now
        self.wip += delta

    def new_part(self) -> Part:
        """Release a new part into station 1."""
        self._next_part += 1
        self._update_wip(+1)
        return Part(self._next_part, self.env.now)

    def exit_part(self, part: Part) -> None:
        """Record a finished part leaving the line."""
        self._update_wip(-1)
        self.exited += 1
        self.sojourns.append(self.env.now - part.t_in)

    def _snapshot(self) -> None:
        for st in self.stations:
            st.set_state(st.state)
        self._update_wip(0)
        self.snapshots.append(
            {
                "t": self.env.now,
                "exited": self.exited,
                "wip": self.wip,
                "wip_area": self.wip_area,
                "levels": [len(b.items) for b in self.buffers],
                "stations": [
                    {**st.time_in, "completed": st.completed, "breakdowns": st.breakdowns} for st in self.stations
                ],
            }
        )

    def _sampler(self) -> Iterator[simpy.Event]:
        while True:
            self._snapshot()
            yield self.env.timeout(SNAPSHOT_INTERVAL)

    def run(self, until: float | None = None) -> "ProductionLine":
        """Advance the simulation to ``until`` seconds (default: one shift)."""
        until = self.config.shift_seconds if until is None else until
        self.env.run(until=until)
        self._snapshot()
        return self

    def kpis(self, t_start: float = 0.0, t_end: float | None = None) -> dict[str, Any]:
        """KPIs over [t_start, t_end] computed from snapshot differences."""
        from src.twin.kpis import window_kpis

        t_end = self.snapshots[-1]["t"] if t_end is None else t_end
        return window_kpis(self.snapshots, self.config, t_start, t_end)

    def rolling_kpis(self, window: float = 1800.0) -> list[dict[str, Any]]:
        """KPIs for consecutive windows of ``window`` seconds."""
        end = self.snapshots[-1]["t"]
        edges = list(np.arange(0.0, end, window)) + [end]
        return [self.kpis(a, b) for a, b in zip(edges[:-1], edges[1:]) if b - a > 0]

    def little_stats(self) -> dict[str, float]:
        """Time-average WIP, throughput rate and mean sojourn for Little's law checks."""
        t = self.snapshots[-1]["t"]
        return {
            "avg_wip": self.wip_area / t,
            "throughput_rate": self.exited / t,
            "mean_sojourn": float(np.mean(self.sojourns)) if self.sojourns else 0.0,
        }

    def result(self, window: float = 1800.0) -> RunResult:
        """Package the finished run as a :class:`RunResult`."""
        k = self.kpis()
        return RunResult(
            seed=self.seed,
            duration=self.snapshots[-1]["t"],
            throughput_per_shift=k["throughput_per_shift"],
            kpis=k,
            rolling=self.rolling_kpis(window),
            events=self.events,
        )


def simulate(config: LineConfig, seed: int = 0, until: float | None = None) -> RunResult:
    """Run one deterministic replication and return its result."""
    return ProductionLine(config, seed).run(until).result()


def replicate(config: LineConfig, seeds: list[int], until: float | None = None) -> list[RunResult]:
    """Run one replication per seed."""
    return [simulate(config, s, until) for s in seeds]
