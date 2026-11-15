"""OpenAI backend and provider selection in ``from_env`` (fake client: no network, no key)."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
from pydantic import BaseModel

from src.llm import AnthropicBackend, LLMClient, OpenAIBackend, UsageMeter, from_env

openai = pytest.importorskip("openai")


class Answer(BaseModel):
    station: int
    confidence: float


class FakeOpenAI:
    """Mimics ``openai.OpenAI().chat.completions.create`` with scripted replies or errors."""

    def __init__(self, script: list[Any]) -> None:
        self.script, self.requests = list(script), []
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=self._create))

    def _create(self, **kwargs: Any) -> Any:
        self.requests.append(kwargs)
        item = self.script.pop(0)
        if isinstance(item, Exception):
            raise item
        content, usage = item
        return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=content))], usage=usage)


def _reply(text: str | None, prompt: int = 11, completion: int = 7) -> tuple[str | None, Any]:
    return text, SimpleNamespace(prompt_tokens=prompt, completion_tokens=completion)


def _rate_limit() -> Exception:
    import httpx

    req = httpx.Request("POST", "https://api.openai.com/v1/chat/completions")
    return openai.RateLimitError("slow down", response=httpx.Response(429, request=req), body=None)


def test_request_shape_and_usage_mapping() -> None:
    fake = FakeOpenAI([_reply('{"station": 2, "confidence": 0.9}')])
    backend = OpenAIBackend("gpt-4.1-mini", client=fake)
    raw = backend.generate("diag", "be terse", "Diagnose.", {}, 321)
    assert (raw.text, raw.input_tokens, raw.output_tokens) == ('{"station": 2, "confidence": 0.9}', 11, 7)
    req = fake.requests[0]
    assert req["model"] == "gpt-4.1-mini" and req["max_completion_tokens"] == 321
    assert req["response_format"] == {"type": "json_object"}
    assert req["messages"] == [{"role": "system", "content": "be terse"}, {"role": "user", "content": "Diagnose."}]


def test_none_content_and_missing_usage_do_not_crash() -> None:
    fake = FakeOpenAI([(None, None)])
    raw = OpenAIBackend("gpt-4.1-mini", client=fake).generate("r", "s", "p", {}, 10)
    assert (raw.text, raw.input_tokens, raw.output_tokens) == ("", 0, 0)


def test_retryable_covers_sdk_rate_limit_connection_and_server_errors() -> None:
    b = OpenAIBackend("gpt-4.1-mini", client=FakeOpenAI([]))
    assert {openai.RateLimitError, openai.APIConnectionError, openai.InternalServerError} <= set(b.retryable)
    assert issubclass(openai.APITimeoutError, b.retryable)  # timeouts are retried through APIConnectionError
    assert not issubclass(openai.AuthenticationError, b.retryable)  # a bad key must fail loudly, not retry


def test_client_retries_rate_limit_then_returns_validated_json(tmp_path: Path) -> None:
    fake = FakeOpenAI([_rate_limit(), _reply('{"station": 3, "confidence": 0.5}')])
    sleeps: list[float] = []
    client = LLMClient(OpenAIBackend("gpt-4.1-mini", client=fake), cache_dir=tmp_path, base_delay=1.0, sleep=sleeps.append)
    meter = UsageMeter()
    out = client.complete_json("diag", "sys", "Diagnose.", {"x": 1}, Answer, meter)
    assert out == Answer(station=3, confidence=0.5) and sleeps == [1.0] and len(fake.requests) == 2
    assert (meter.input_tokens, meter.output_tokens) == (11, 7)
    again = client.complete_json("diag", "sys", "Diagnose.", {"x": 1}, Answer, meter)  # served from cache
    assert again == out and len(fake.requests) == 2 and meter.cache_hits == 1


def test_cache_does_not_mix_providers_or_models(tmp_path: Path) -> None:
    a = LLMClient(OpenAIBackend("gpt-4.1-mini", client=FakeOpenAI([_reply('{"station": 1, "confidence": 1}')])), cache_dir=tmp_path)
    b = LLMClient(OpenAIBackend("gpt-4.1", client=FakeOpenAI([_reply('{"station": 2, "confidence": 1}')])), cache_dir=tmp_path)
    assert a.complete_json("d", "s", "p", {}, Answer).station == 1
    assert b.complete_json("d", "s", "p", {}, Answer).station == 2


# --- provider selection ----------------------------------------------------------------


@pytest.fixture
def clean_env(monkeypatch: pytest.MonkeyPatch) -> pytest.MonkeyPatch:
    for var in ["ANTHROPIC_API_KEY", "OPENAI_API_KEY", "LLM_PROVIDER", "LLM_MODE", "LLM_MODEL", "OPENAI_MODEL"]:
        monkeypatch.delenv(var, raising=False)
    monkeypatch.setattr("dotenv.load_dotenv", lambda *a, **k: False)  # keep the developer's real .env out of the test
    return monkeypatch


def test_openai_key_alone_never_leaves_mock_mode(clean_env: pytest.MonkeyPatch) -> None:
    clean_env.setenv("OPENAI_API_KEY", "sk-test")  # often set for unrelated tools: must not start paid calls here
    assert from_env().is_mock


def test_explicit_openai_provider_uses_default_model(clean_env: pytest.MonkeyPatch, tmp_path: Path) -> None:
    clean_env.setenv("LLM_PROVIDER", "openai")
    clean_env.setenv("OPENAI_API_KEY", "sk-test")
    client = from_env(cache_dir=tmp_path)
    assert isinstance(client.backend, OpenAIBackend) and client.model == "gpt-4.1-mini" and not client.is_mock


def test_openai_model_comes_from_openai_model_not_llm_model(clean_env: pytest.MonkeyPatch, tmp_path: Path) -> None:
    clean_env.setenv("LLM_PROVIDER", "openai")
    clean_env.setenv("OPENAI_API_KEY", "sk-test")
    clean_env.setenv("LLM_MODEL", "claude-haiku-5-5")  # the Anthropic model name must not leak into an OpenAI call
    assert from_env(cache_dir=tmp_path).model == "gpt-4.1-mini"
    clean_env.setenv("OPENAI_MODEL", "gpt-4.1")
    assert from_env(cache_dir=tmp_path).model == "gpt-4.1"


def test_anthropic_stays_default_when_both_keys_are_set_and_provider_switches_explicitly(clean_env: pytest.MonkeyPatch, tmp_path: Path) -> None:
    clean_env.setenv("ANTHROPIC_API_KEY", "sk-ant-test")
    clean_env.setenv("OPENAI_API_KEY", "sk-test")
    assert isinstance(from_env(cache_dir=tmp_path).backend, AnthropicBackend)
    clean_env.setenv("LLM_PROVIDER", "openai")
    assert isinstance(from_env(cache_dir=tmp_path).backend, OpenAIBackend)


def test_no_keys_means_mock_even_with_openai_provider(clean_env: pytest.MonkeyPatch) -> None:
    clean_env.setenv("LLM_PROVIDER", "openai")
    assert from_env().is_mock


def test_real_mode_with_openai_and_no_key_names_the_missing_variable(clean_env: pytest.MonkeyPatch) -> None:
    clean_env.setenv("LLM_PROVIDER", "openai")
    clean_env.setenv("LLM_MODE", "real")
    with pytest.raises(RuntimeError, match="OPENAI_API_KEY"):
        from_env()


def test_unknown_provider_fails_loudly(clean_env: pytest.MonkeyPatch) -> None:
    clean_env.setenv("LLM_PROVIDER", "gemini")
    with pytest.raises(RuntimeError, match="LLM_PROVIDER"):
        from_env()


def test_mock_mode_can_be_forced_even_with_a_key(clean_env: pytest.MonkeyPatch) -> None:
    clean_env.setenv("OPENAI_API_KEY", "sk-test")
    clean_env.setenv("LLM_MODE", "mock")
    assert from_env().is_mock
