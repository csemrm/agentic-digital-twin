"""Constraint validation and application of typed actions."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

from pydantic import ValidationError

from src.actions.schema import ACTION_ADAPTER, Action, AddBuffer, ChangeMaintenance, RebalanceTask
from src.twin.config import LineConfig

logger = logging.getLogger("actions")

MAX_BUFFER_ADD = 5
MAX_BUFFER_CAPACITY = 12
MAX_REBALANCE_FRACTION = 0.30
MAX_MTBF_MULTIPLIER = 2.0
MIN_MTTR_MULTIPLIER = 0.5


@dataclass
class ActionResult:
    """Outcome of validating (and optionally applying) a proposed action."""

    ok: bool
    action: Action | None
    reason: str = ""
    config: LineConfig | None = None


@dataclass
class RejectionLog:
    """Collects rejected proposals with reasons."""

    entries: list[dict[str, Any]] = field(default_factory=list)

    def add(self, raw: Any, reason: str) -> None:
        """Record a rejection and emit it to the ``actions`` logger."""
        self.entries.append({"proposal": raw if isinstance(raw, dict) else repr(raw), "reason": reason})
        logger.warning("rejected action %s: %s", raw, reason)


def parse_action(raw: Any) -> Action:
    """Parse ``raw`` (dict or action model) into a typed action; raises ValidationError."""
    if isinstance(raw, (AddBuffer, RebalanceTask, ChangeMaintenance)):
        return raw
    return ACTION_ADAPTER.validate_python(raw)


def check_constraints(action: Action, config: LineConfig) -> str | None:
    """Return a rejection reason if ``action`` violates a constraint on ``config``, else None."""
    n = config.n_stations
    if isinstance(action, AddBuffer):
        if not 1 <= action.station <= n - 1:
            return f"add_buffer: station must be in 1..{n - 1} (last station has no buffer)"
        if not 1 <= action.size <= MAX_BUFFER_ADD:
            return f"add_buffer: size must be in 1..{MAX_BUFFER_ADD}"
        new_cap = (config.station(action.station).buffer_after or 0) + action.size
        if new_cap > MAX_BUFFER_CAPACITY:
            return f"add_buffer: resulting capacity {new_cap} exceeds limit {MAX_BUFFER_CAPACITY}"
    elif isinstance(action, RebalanceTask):
        if not (1 <= action.from_station <= n and 1 <= action.to_station <= n):
            return f"rebalance_task: stations must be in 1..{n}"
        if abs(action.from_station - action.to_station) != 1:
            return "rebalance_task: stations must be adjacent"
        if not 0 < action.fraction <= MAX_REBALANCE_FRACTION:
            return f"rebalance_task: fraction must be in (0, {MAX_REBALANCE_FRACTION}]"
    elif isinstance(action, ChangeMaintenance):
        if not 1 <= action.station <= n:
            return f"change_maintenance: station must be in 1..{n}"
        if config.station(action.station).mtbf is None:
            return "change_maintenance: station has no failure model"
        if not 1.0 <= action.mtbf_multiplier <= MAX_MTBF_MULTIPLIER:
            return f"change_maintenance: mtbf_multiplier must be in [1, {MAX_MTBF_MULTIPLIER}]"
        if not MIN_MTTR_MULTIPLIER <= action.mttr_multiplier <= 1.0:
            return f"change_maintenance: mttr_multiplier must be in [{MIN_MTTR_MULTIPLIER}, 1]"
        if action.mtbf_multiplier == 1.0 and action.mttr_multiplier == 1.0:
            return "change_maintenance: no-op change"
    return None


def apply_action(config: LineConfig, action: Action) -> LineConfig:
    """Return a modified deep copy of ``config``; the action must already be validated."""
    new = config.model_copy(deep=True)
    if isinstance(action, AddBuffer):
        st = new.station(action.station)
        new.stations[action.station - 1] = st.model_copy(update={"buffer_after": (st.buffer_after or 0) + action.size})
    elif isinstance(action, RebalanceTask):
        src, dst = new.station(action.from_station), new.station(action.to_station)
        moved = action.fraction * src.cycle_time_mean
        new.stations[action.from_station - 1] = src.model_copy(update={"cycle_time_mean": src.cycle_time_mean - moved})
        new.stations[action.to_station - 1] = dst.model_copy(update={"cycle_time_mean": dst.cycle_time_mean + moved})
    elif isinstance(action, ChangeMaintenance):
        st = new.station(action.station)
        assert st.mtbf is not None
        new.stations[action.station - 1] = st.model_copy(
            update={"mtbf": st.mtbf * action.mtbf_multiplier, "mttr": st.mttr * action.mttr_multiplier}
        )
    return new


def validate_and_apply(raw: Any, config: LineConfig, log: RejectionLog | None = None) -> ActionResult:
    """Parse, constraint-check and apply ``raw``; rejections are logged with their reason."""
    log = log if log is not None else RejectionLog()
    try:
        action = parse_action(raw)
    except ValidationError as exc:
        reason = "schema: " + "; ".join(f"{'.'.join(map(str, e['loc']))}: {e['msg']}" for e in exc.errors())
        log.add(raw, reason)
        return ActionResult(False, None, reason)
    reason = check_constraints(action, config)
    if reason is not None:
        log.add(raw, reason)
        return ActionResult(False, action, reason)
    return ActionResult(True, action, "", apply_action(config, action))
