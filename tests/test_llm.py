"""LLM wrapper: mock mode, cache, retry/backoff, JSON validation, metering."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from pydantic import BaseModel

from src.llm import LLMClient, LLMOutputError, MockBackend, RawCompletion, UsageMeter, from_env


class Answer(BaseModel):
    station: int
    confidence: float


class RateLimited(Exception):
    """Stand-in for the SDK's rate-limit error."""


class ScriptedBackend:
    """Backend returning scripted texts / raising scripted errors, counting calls."""

    name = "fake-model"
    retryable = (RateLimited,)
    cacheable = True

    def __init__(self, script: list[Any]) -> None:
        self.script = list(script)
        self.calls = 0

    def generate(self, role: str, system: str, prompt: str, payload: dict[str, Any], max_tokens: int) -> RawCompletion:
        self.calls += 1
        item = self.script.pop(0)
        if isinstance(item, Exception):
            raise item
        return RawCompletion(item, 10, 5)


def _ask(client: LLMClient, meter: UsageMeter | None = None) -> Answer:
    return client.complete_json("diag", "sys", "Diagnose.", {"x": 1}, Answer, meter)


def test_mock_mode_needs_no_key_and_is_deterministic() -> None:
    handlers = {"diag": lambda p: {"station": p["x"] + 1, "confidence": 0.9}}
    client = LLMClient(MockBackend(handlers))
    assert client.is_mock
    assert _ask(client) == _ask(client) == Answer(station=2, confidence=0.9)


def test_mock_missing_handler_raises() -> None:
    with pytest.raises(KeyError):
        _ask(LLMClient(MockBackend()))


def test_meter_counts_steps_and_tokens() -> None:
    client = LLMClient(MockBackend({"diag": lambda p: {"station": 1, "confidence": 0.5}}))
    meter = UsageMeter()
    _ask(client, meter)
    _ask(client, meter)
    assert meter.steps == 2 and meter.by_role == {"diag": 2}
    assert meter.input_tokens > 0 and meter.output_tokens > 0
    assert meter.total_tokens == meter.input_tokens + meter.output_tokens


def test_disk_cache_avoids_second_backend_call(tmp_path: Path) -> None:
    backend = ScriptedBackend(['{"station": 3, "confidence": 0.7}'])
    client = LLMClient(backend, cache_dir=tmp_path)
    meter = UsageMeter()
    first, second = _ask(client, meter), _ask(client, meter)
    assert first == second and backend.calls == 1
    assert meter.steps == 2 and meter.cache_hits == 1
    assert len(list(tmp_path.glob("*.json"))) == 1


def test_cache_key_depends_on_model(tmp_path: Path) -> None:
    a, b = ScriptedBackend(['{"station": 1, "confidence": 1}']), ScriptedBackend(['{"station": 2, "confidence": 1}'])
    b.name = "other-model"
    assert _ask(LLMClient(a, cache_dir=tmp_path)).station == 1
    assert _ask(LLMClient(b, cache_dir=tmp_path)).station == 2


def test_rate_limit_retries_with_exponential_backoff() -> None:
    sleeps: list[float] = []
    backend = ScriptedBackend([RateLimited(), RateLimited(), '{"station": 1, "confidence": 0.5}'])
    client = LLMClient(backend, base_delay=1.0, sleep=sleeps.append)
    assert _ask(client).station == 1
    assert sleeps == [1.0, 2.0] and backend.calls == 3


def test_rate_limit_gives_up_after_max_retries() -> None:
    backend = ScriptedBackend([RateLimited()] * 3)
    client = LLMClient(backend, max_retries=2, sleep=lambda s: None)
    with pytest.raises(RateLimited):
        _ask(client)
    assert backend.calls == 3


def test_fenced_json_is_accepted() -> None:
    backend = ScriptedBackend(['Sure!\n```json\n{"station": 4, "confidence": 0.6}\n```'])
    assert _ask(LLMClient(backend)).station == 4


def test_invalid_json_triggers_repair_and_counts_steps(tmp_path: Path) -> None:
    backend = ScriptedBackend(["not json", '{"station": 2, "confidence": 0.8}'])
    client = LLMClient(backend, cache_dir=tmp_path)
    meter = UsageMeter()
    assert _ask(client, meter).station == 2
    assert meter.steps == 2
    assert len(list(tmp_path.glob("*.json"))) == 1  # only the valid reply is cached


def test_schema_violation_raises_after_repairs() -> None:
    backend = ScriptedBackend(['{"station": "x"}', '{"station": "y"}'])
    with pytest.raises(LLMOutputError):
        _ask(LLMClient(backend, repair_attempts=1))


def test_from_env_defaults_to_mock_without_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("LLM_MODE", raising=False)
    assert from_env().is_mock


def test_real_mode_without_key_fails_loudly(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.setenv("LLM_MODE", "real")
    with pytest.raises(RuntimeError):
        from_env()
