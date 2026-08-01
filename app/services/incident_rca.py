from __future__ import annotations

import logging
from collections import defaultdict
from typing import Any

from app.config import get_settings
from app.models import Alert, IncidentAnalysis
from app.services.llm_adapter import LLMAdapter

logger = logging.getLogger(__name__)


def normalize_alert(alert: dict[str, Any]) -> Alert:
    """Normalize alert payloads from Prometheus or ELK-style sources."""
    if not isinstance(alert, dict):
        raise ValueError("Each alert must be a dictionary")

    labels = alert.get("labels", {}) if isinstance(alert.get("labels"), dict) else {}
    service = alert.get("service") or alert.get("service_name") or labels.get("service") or "unknown"
    severity = alert.get("severity") or alert.get("level") or labels.get("severity") or "warning"
    summary = alert.get("summary") or alert.get("message") or alert.get("title") or "incident alert"
    timestamp = alert.get("timestamp") or alert.get("@timestamp") or alert.get("time") or ""
    source = alert.get("source") or get_settings().default_source

    return Alert(
        service=str(service).lower(),
        severity=str(severity).lower(),
        summary=str(summary),
        timestamp=str(timestamp),
        source=str(source),
        raw=alert,
    )


def build_summary(clusters: list[dict[str, Any]], alerts: list[Alert]) -> str:
    """Create a concise incident summary using the clustered alerts."""
    if not clusters:
        return "No incident clusters available."

    primary_service = max(clusters, key=lambda cluster: cluster["alert_count"])["service"]
    total_alerts = sum(cluster["alert_count"] for cluster in clusters)
    sources = sorted({alert.source for alert in alerts})
    return (
        f"Incident detected across {len(clusters)} service cluster(s) from {', '.join(sources)}. "
        f"The highest-impact service is {primary_service}, with {total_alerts} alerts observed."
    )


def draft_recommendations(primary_service: str) -> list[str]:
    """Generate a deterministic set of draft runbook steps."""
    return [
        f"Inspect the {primary_service} dashboard, recent deployments, and SLO burn-rate charts.",
        "Correlate the top error signatures with recent config changes and dependency latency spikes.",
        f"If {primary_service} remains impaired, page the owning team, prepare a rollback, and document mitigation steps.",
    ]


def analyze_incident(alerts: list[dict[str, Any]], llm_adapter: LLMAdapter | None = None) -> IncidentAnalysis:
    """Create a production-style RCA summary from incident alerts."""
    settings = get_settings()
    logger.info("Starting incident analysis for %d alerts", len(alerts))

    normalized_alerts = [normalize_alert(alert) for alert in alerts]
    clusters: list[dict[str, Any]] = []
    service_groups: dict[str, list[Alert]] = defaultdict(list)

    for alert in normalized_alerts:
        service_groups[alert.service].append(alert)

    for service, items in sorted(service_groups.items()):
        severities = sorted({item.severity for item in items})
        summaries = "; ".join(item.summary for item in items)
        clusters.append(
            {
                "service": service,
                "alert_count": len(items),
                "severities": severities,
                "summary": summaries,
            }
        )

    primary_service = max(clusters, key=lambda cluster: cluster["alert_count"])["service"]
    incident_summary = build_summary(clusters, normalized_alerts)
    recommendations = draft_recommendations(primary_service)

    if settings.enable_llm and llm_adapter is not None:
        incident_summary = llm_adapter.summarize(clusters, incident_summary)

    logger.info("Completed incident analysis for service %s", primary_service)
    return IncidentAnalysis(
        clusters=clusters,
        summary=incident_summary,
        recommendations=recommendations,
    )
