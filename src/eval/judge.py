"""LLM-as-judge rubric for diagnosis explanation quality (1-5)."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from src.llm import LLMClient, UsageMeter

JUDGE_SYSTEM = (
    "You grade the quality of a diagnosis explanation written by an AI agent for a production-line supervisor. "
    "Score three dimensions from 1 (poor) to 5 (excellent): correctness (does the claimed bottleneck station and fault "
    "match the reference answer; 5 = both correct, 3 = right station wrong fault, 1 = wrong), evidence (does it cite "
    "specific KPI numbers from the observation that support the claim; 1 = none, 5 = several accurate figures), clarity "
    "(plain, concise, actionable for a supervisor). overall = mean of the three. Reply with scores only."
)


class JudgeScore(BaseModel):
    """Rubric scores returned by the judge."""

    correctness: int = Field(ge=1, le=5)
    evidence: int = Field(ge=1, le=5)
    clarity: int = Field(ge=1, le=5)
    overall: float = Field(ge=1, le=5)
    comment: str = ""


def judge_explanation(
    client: LLMClient, diagnosis: dict[str, Any], truth: dict[str, Any], observation: dict[str, Any], meter: UsageMeter | None = None
) -> JudgeScore:
    """Score one diagnosis explanation against the scenario's reference label and the observed KPIs."""
    payload = {
        "explanation": diagnosis.get("explanation", ""),
        "claimed": {"station": diagnosis.get("bottleneck_station"), "fault_type": diagnosis.get("fault_type")},
        "reference": truth,
        "observation": observation,
    }
    return client.complete_json("judge", JUDGE_SYSTEM, "Grade this explanation.", payload, JudgeScore, meter, max_tokens=300)
