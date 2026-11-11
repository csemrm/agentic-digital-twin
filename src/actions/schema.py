"""Typed action set agents may propose. Anything outside this schema is rejected."""

from __future__ import annotations

from typing import Annotated, Literal, Union

from pydantic import BaseModel, ConfigDict, Field, TypeAdapter


class AddBuffer(BaseModel):
    """Add ``size`` slots to the buffer after ``station``."""

    model_config = ConfigDict(extra="forbid")
    type: Literal["add_buffer"] = "add_buffer"
    station: int
    size: int


class RebalanceTask(BaseModel):
    """Move ``fraction`` of ``from_station``'s work content to ``to_station``."""

    model_config = ConfigDict(extra="forbid")
    type: Literal["rebalance_task"] = "rebalance_task"
    from_station: int
    to_station: int
    fraction: float


class ChangeMaintenance(BaseModel):
    """Scale MTBF and/or MTTR of ``station`` (e.g. preventive maintenance, spares)."""

    model_config = ConfigDict(extra="forbid")
    type: Literal["change_maintenance"] = "change_maintenance"
    station: int
    mtbf_multiplier: float = 1.0
    mttr_multiplier: float = 1.0


Action = Annotated[Union[AddBuffer, RebalanceTask, ChangeMaintenance], Field(discriminator="type")]
ACTION_ADAPTER: TypeAdapter[Action] = TypeAdapter(Action)

ACTION_SCHEMA_HINT = (
    '{"type":"add_buffer","station":int,"size":int} | '
    '{"type":"rebalance_task","from_station":int,"to_station":int,"fraction":float} | '
    '{"type":"change_maintenance","station":int,"mtbf_multiplier":float,"mttr_multiplier":float}'
)
