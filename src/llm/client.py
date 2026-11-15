"""LLM client: disk cache, retry/backoff, usage metering, validated JSON output."""

from __future__ import annotations

import hashlib
import json
import logging
import os
import re
import time
from pathlib import Path
from typing import Any, Callable, TypeVar

from pydantic import BaseModel, ValidationError

from src.llm.backends import AnthropicBackend, Backend, MockBackend, MockHandler, OpenAIBackend, RawCompletion
from src.llm.usage import UsageMeter

logger = logging.getLogger("llm")

DEFAULT_MODEL = "claude-haiku-5-5"
DEFAULT_OPENAI_MODEL = "gpt-4.1-mini"
DEFAULT_CACHE_DIR = Path("results/llm_cache")
PROVIDERS = {  # provider -> (API key variable, model variable, default model)
    "anthropic": ("ANTHROPIC_API_KEY", "LLM_MODEL", DEFAULT_MODEL),
    "openai": ("OPENAI_API_KEY", "OPENAI_MODEL", DEFAULT_OPENAI_MODEL),
}

T = TypeVar("T", bound=BaseModel)


class LLMOutputError(RuntimeError):
    """Raised when the model never returns JSON that validates against the schema."""


def extract_json(text: str) -> Any:
    """Parse the first JSON object in ``text``, tolerating code fences and prose."""
    cleaned = re.sub(r"```(?:json)?", "", text).strip()
    start, end = cleaned.find("{"), cleaned.rfind("}")
    if start == -1 or end <= start:
        raise ValueError("no JSON object found")
    return json.loads(cleaned[start : end + 1])


def build_prompt(instruction: str, payload: dict[str, Any], schema: type[BaseModel]) -> str:
    """Compose a compact user prompt: instruction, input JSON, required output schema."""
    return (
        f"{instruction}\n\nInput:\n{json.dumps(payload, separators=(',', ':'), sort_keys=True)}\n\n"
        f"Reply with ONLY one JSON object matching this JSON Schema:\n"
        f"{json.dumps(schema.model_json_schema(), separators=(',', ':'))}"
    )


class LLMClient:
    """Thin wrapper adding caching, retries and schema-validated JSON to a backend."""

    def __init__(
        self,
        backend: Backend,
        cache_dir: Path | None = None,
        max_retries: int = 4,
        base_delay: float = 1.0,
        repair_attempts: int = 1,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self.backend = backend
        self.cache_dir = cache_dir if backend.cacheable else None
        self.max_retries = max_retries
        self.base_delay = base_delay
        self.repair_attempts = repair_attempts
        self._sleep = sleep
        if self.cache_dir is not None:
            self.cache_dir.mkdir(parents=True, exist_ok=True)

    @property
    def model(self) -> str:
        """Model name reported by the backend (``mock`` offline)."""
        return self.backend.name

    @property
    def is_mock(self) -> bool:
        """True when responses are scripted rather than from a real model."""
        return isinstance(self.backend, MockBackend)

    def _cache_path(self, system: str, prompt: str) -> Path | None:
        if self.cache_dir is None:
            return None
        key = hashlib.sha256(json.dumps([self.model, system, prompt]).encode()).hexdigest()
        return self.cache_dir / f"{key}.json"

    def _call_backend(self, role: str, system: str, prompt: str, payload: dict[str, Any], max_tokens: int) -> RawCompletion:
        for attempt in range(self.max_retries + 1):
            try:
                return self.backend.generate(role, system, prompt, payload, max_tokens)
            except self.backend.retryable as exc:
                if attempt == self.max_retries:
                    raise
                delay = self.base_delay * 2**attempt
                logger.warning("retryable LLM error (%s); sleeping %.1fs", type(exc).__name__, delay)
                self._sleep(delay)
        raise AssertionError("unreachable")

    def _fetch(self, role: str, system: str, prompt: str, payload: dict[str, Any], max_tokens: int) -> tuple[RawCompletion, bool]:
        path = self._cache_path(system, prompt)
        if path is not None and path.exists():
            data = json.loads(path.read_text())
            return RawCompletion(data["text"], data["input_tokens"], data["output_tokens"]), True
        return self._call_backend(role, system, prompt, payload, max_tokens), False

    def _store(self, system: str, prompt: str, raw: RawCompletion) -> None:
        path = self._cache_path(system, prompt)
        if path is not None:
            path.write_text(json.dumps({"text": raw.text, "input_tokens": raw.input_tokens, "output_tokens": raw.output_tokens}))

    def complete_json(
        self,
        role: str,
        system: str,
        instruction: str,
        payload: dict[str, Any],
        schema: type[T],
        meter: UsageMeter | None = None,
        max_tokens: int = 800,
    ) -> T:
        """Ask the model for a ``schema``-valid JSON object.

        Every call (including cache hits and repair attempts) is recorded on
        ``meter``. Invalid output triggers up to ``repair_attempts`` re-asks
        with the validation error appended; invalid replies are never cached.
        """
        base_prompt = build_prompt(instruction, payload, schema)
        prompt, last_error = base_prompt, ""
        for _ in range(self.repair_attempts + 1):
            raw, cached = self._fetch(role, system, prompt, payload, max_tokens)
            if meter is not None:
                meter.record(role, raw.input_tokens, raw.output_tokens, cached)
            try:
                result = schema.model_validate(extract_json(raw.text))
            except (ValueError, ValidationError) as exc:
                last_error = str(exc)[:300]
                logger.warning("invalid %s output: %s", role, last_error)
                prompt = f"{base_prompt}\n\nYour previous reply was invalid ({last_error}). Reply with ONLY valid JSON."
                continue
            if not cached:
                self._store(system, prompt, raw)
            return result
        raise LLMOutputError(f"{role}: no valid JSON after {self.repair_attempts + 1} attempts: {last_error}")


def _provider() -> str:
    """``LLM_PROVIDER`` (default ``anthropic``).

    Deliberately explicit: ``OPENAI_API_KEY`` is often set for unrelated tools, so its mere presence must
    not switch this project from free mock mode to paid calls.
    """
    provider = os.environ.get("LLM_PROVIDER", "").strip().lower() or "anthropic"
    if provider not in PROVIDERS:
        raise RuntimeError(f"LLM_PROVIDER must be one of {sorted(PROVIDERS)}, got {provider!r}")
    return provider


def from_env(handlers: dict[str, MockHandler] | None = None, cache_dir: Path | None = None) -> LLMClient:
    """Build a client from env vars.

    Provider: ``LLM_PROVIDER`` = ``anthropic`` (default; key ``ANTHROPIC_API_KEY``, model ``LLM_MODEL``) or
    ``openai`` (key ``OPENAI_API_KEY``, model ``OPENAI_MODEL``, default ``gpt-4.1-mini``). OpenAI is used only when
    ``LLM_PROVIDER=openai`` is set explicitly. Defaults to mock mode unless the chosen provider's key is set and
    ``LLM_MODE`` is not ``mock``.
    """
    try:
        from dotenv import load_dotenv

        load_dotenv()
    except ImportError:  # pragma: no cover - dotenv is a declared dependency
        pass
    provider = _provider()
    key_var, model_var, default_model = PROVIDERS[provider]
    key = os.environ.get(key_var, "")
    mode = os.environ.get("LLM_MODE") or ("real" if key else "mock")
    if mode == "real":
        if not key:
            raise RuntimeError(f"LLM_MODE=real with provider {provider!r} requires {key_var}")
        model = os.environ.get(model_var) or default_model
        backend: Backend = OpenAIBackend(model, key) if provider == "openai" else AnthropicBackend(model, key)
        return LLMClient(backend, cache_dir=cache_dir or DEFAULT_CACHE_DIR)
    return LLMClient(MockBackend(handlers))
