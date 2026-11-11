"""Monitor, Diagnosis, Simulation and Supervisor-gate agents plus the LangGraph loop."""

from src.agents.gate import SimulatedApprover
from src.agents.graph import Pipeline
from src.agents.mock_roles import MOCK_HANDLERS
from src.agents.types import PipelineSettings, RunRecord
from src.llm import LLMClient, MockBackend, from_env


def default_client() -> LLMClient:
    """LLM client from env vars; mock handlers are wired in for offline mode."""
    return from_env(MOCK_HANDLERS)


def mock_client() -> LLMClient:
    """Always-offline client with scripted role handlers (used by tests)."""
    return LLMClient(MockBackend(MOCK_HANDLERS))


__all__ = ["Pipeline", "PipelineSettings", "RunRecord", "SimulatedApprover", "MOCK_HANDLERS", "default_client", "mock_client"]
