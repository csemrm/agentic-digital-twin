"""LLM backends: the real Anthropic API and a deterministic offline mock."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Callable, Protocol

MockHandler = Callable[[dict[str, Any]], dict[str, Any]]


@dataclass
class RawCompletion:
    """Raw text and token counts returned by a backend."""

    text: str
    input_tokens: int
    output_tokens: int


class Backend(Protocol):
    """Interface the client talks to."""

    name: str
    retryable: tuple[type[BaseException], ...]
    cacheable: bool

    def generate(self, role: str, system: str, prompt: str, payload: dict[str, Any], max_tokens: int) -> RawCompletion:
        """Produce a completion for one request."""
        ...


def estimate_tokens(text: str) -> int:
    """Rough token estimate (about 4 characters per token) used in mock mode."""
    return max(1, len(text) // 4)


class MockBackend:
    """Deterministic scripted responses; needs no API key.

    ``handlers`` maps a role name to a function from the structured payload to
    a response dict. Token counts are character-based estimates.
    """

    name = "mock"
    retryable: tuple[type[BaseException], ...] = ()
    cacheable = False

    def __init__(self, handlers: dict[str, MockHandler] | None = None) -> None:
        self.handlers = dict(handlers or {})

    def generate(self, role: str, system: str, prompt: str, payload: dict[str, Any], max_tokens: int) -> RawCompletion:
        """Dispatch to the handler registered for ``role``."""
        if role not in self.handlers:
            raise KeyError(f"no mock handler registered for role {role!r}")
        text = json.dumps(self.handlers[role](payload), sort_keys=True)
        return RawCompletion(text, estimate_tokens(system) + estimate_tokens(prompt), estimate_tokens(text))


class AnthropicBackend:
    """Calls the Anthropic Messages API via the official SDK."""

    cacheable = True

    def __init__(self, model: str, api_key: str | None = None) -> None:
        import anthropic

        self.name = model
        self._client = anthropic.Anthropic(api_key=api_key)
        self.retryable = (
            anthropic.RateLimitError,
            anthropic.APIConnectionError,
            anthropic.InternalServerError,
        )

    def generate(self, role: str, system: str, prompt: str, payload: dict[str, Any], max_tokens: int) -> RawCompletion:
        """Send one request and return text plus reported token usage."""
        msg = self._client.messages.create(
            model=self.name,
            max_tokens=max_tokens,
            system=system,
            messages=[{"role": "user", "content": prompt}],
        )
        text = "".join(block.text for block in msg.content if getattr(block, "type", "") == "text")
        return RawCompletion(text, msg.usage.input_tokens, msg.usage.output_tokens)
