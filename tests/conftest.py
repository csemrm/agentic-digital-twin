"""Test isolation: the suite must never read a developer's ``.env`` or shell API keys.

``from_env`` calls ``load_dotenv()`` and picks a provider from the environment, so without this a
configured ``.env`` (or an exported ``OPENAI_API_KEY``) silently flips tests into real, paid mode.
Tests that need a specific configuration set it themselves with ``monkeypatch.setenv``.
"""

from __future__ import annotations

import pytest

LLM_ENV_VARS = ["ANTHROPIC_API_KEY", "OPENAI_API_KEY", "LLM_PROVIDER", "LLM_MODE", "LLM_MODEL", "OPENAI_MODEL"]


@pytest.fixture(autouse=True)
def _isolate_llm_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    for var in LLM_ENV_VARS:
        monkeypatch.delenv(var, raising=False)
    monkeypatch.setattr("dotenv.load_dotenv", lambda *args, **kwargs: False)
