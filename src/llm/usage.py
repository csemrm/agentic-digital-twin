"""Per-run LLM usage accounting (steps and tokens)."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class UsageMeter:
    """Counts logical LLM steps and tokens for one run.

    Cached responses still count as steps and tokens (what a fresh run would
    spend) and are also tallied in ``cache_hits``.
    """

    steps: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    cache_hits: int = 0
    by_role: dict[str, int] = field(default_factory=dict)

    def record(self, role: str, input_tokens: int, output_tokens: int, cached: bool) -> None:
        """Add one LLM call to the totals."""
        self.steps += 1
        self.input_tokens += input_tokens
        self.output_tokens += output_tokens
        self.cache_hits += int(cached)
        self.by_role[role] = self.by_role.get(role, 0) + 1

    @property
    def total_tokens(self) -> int:
        """Input plus output tokens."""
        return self.input_tokens + self.output_tokens

    def as_dict(self) -> dict[str, object]:
        """Plain-dict view for logging and CSVs."""
        return {
            "steps": self.steps,
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
            "total_tokens": self.total_tokens,
            "cache_hits": self.cache_hits,
            "by_role": dict(self.by_role),
        }
