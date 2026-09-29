from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

# Severity first, volume second — one critical outranks several warnings.
SEVERITY_WEIGHTS: dict[str, int] = {
    "critical": 8,
    "fatal": 8,
    "page": 8,
    "error": 4,
    "err": 4,
    "warning": 2,
    "warn": 2,
    "info": 1,
    "debug": 1,
}
DEFAULT_SEVERITY_WEIGHT = 2


def severity_weight(severity: str) -> int:
    return SEVERITY_WEIGHTS.get(str(severity).strip().lower(), DEFAULT_SEVERITY_WEIGHT)


@dataclass
class Alert:
    service: str
    severity: str
    summary: str
    timestamp: str = ""
    source: str = "unknown"
    raw: dict[str, Any] = field(default_factory=dict)
    epoch: float | None = None
    """Parsed ``timestamp`` in seconds, or None when it could not be parsed."""


@dataclass
class IncidentAnalysis:
    clusters: list[dict[str, Any]]
    summary: str
    recommendations: list[str]
    primary_service: str = "unknown"
    alert_count: int = 0
    window_seconds: float | None = None
    """Elapsed time between the first and last correlated alert, when known."""
    llm_provider: str = "offline"
