from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class Alert:
    service: str
    severity: str
    summary: str
    timestamp: str = ""
    source: str = "unknown"
    raw: dict[str, Any] = field(default_factory=dict)


@dataclass
class IncidentAnalysis:
    clusters: list[dict[str, Any]]
    summary: str
    recommendations: list[str]
