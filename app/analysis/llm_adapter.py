from __future__ import annotations

from typing import Any


class LLMAdapter:
    """Thin adapter for future integration with an external LLM provider."""

    def __init__(self, provider: str = "mock", model: str | None = None) -> None:
        self.provider = provider
        self.model = model

    def summarize(self, clusters: list[dict[str, Any]], incident_summary: str) -> str:
        if self.provider == "mock":
            return incident_summary
        raise NotImplementedError(f"LLM provider '{self.provider}' is not configured")
