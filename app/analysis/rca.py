from __future__ import annotations

import logging
import re
from collections import defaultdict
from datetime import datetime
from typing import Any

from app.analysis.llm_adapter import LLMAdapter
from app.core.config import get_settings
from app.core.models import Alert, IncidentAnalysis, severity_weight

logger = logging.getLogger(__name__)


def parse_timestamp(value: str) -> float | None:
    """Parse the timestamp formats that actually turn up in alert payloads."""
    if not value:
        return None

    text = str(value).strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"

    try:
        return datetime.fromisoformat(text).timestamp()
    except ValueError:
        pass

    # Prometheus and some exporters send epoch seconds or milliseconds.
    try:
        number = float(text)
    except ValueError:
        return None
    # Anything past ~2001 in milliseconds is out of range as seconds.
    return number / 1000.0 if number > 1e11 else number


def normalize_alert(alert: dict[str, Any]) -> Alert:
    if not isinstance(alert, dict):
        raise ValueError("Each alert must be a dictionary")

    labels = alert.get("labels", {}) if isinstance(alert.get("labels"), dict) else {}
    annotations = (
        alert.get("annotations", {}) if isinstance(alert.get("annotations"), dict) else {}
    )

    service = (
        alert.get("service")
        or alert.get("service_name")
        or labels.get("service")
        or labels.get("job")
        or "unknown"
    )
    severity = (
        alert.get("severity") or alert.get("level") or labels.get("severity") or "warning"
    )
    summary = (
        alert.get("summary")
        or alert.get("message")
        or alert.get("title")
        or annotations.get("summary")
        or annotations.get("description")
        or labels.get("alertname")
        or "incident alert"
    )
    timestamp = (
        alert.get("timestamp")
        or alert.get("@timestamp")
        or alert.get("time")
        or alert.get("startsAt")
        or ""
    )
    source = alert.get("source") or get_settings().default_source

    return Alert(
        service=str(service).lower(),
        severity=str(severity).lower(),
        summary=str(summary),
        timestamp=str(timestamp),
        source=str(source),
        raw=alert,
        epoch=parse_timestamp(str(timestamp)),
    )


def build_clusters(alerts: list[Alert]) -> list[dict[str, Any]]:
    """Group alerts by service and rank the groups by severity-weighted impact."""
    groups: dict[str, list[Alert]] = defaultdict(list)
    for alert in alerts:
        groups[alert.service].append(alert)

    clusters: list[dict[str, Any]] = []
    for service, items in groups.items():
        epochs = [item.epoch for item in items if item.epoch is not None]
        clusters.append(
            {
                "service": service,
                "alert_count": len(items),
                "severities": sorted({item.severity for item in items}),
                "summary": "; ".join(dict.fromkeys(item.summary for item in items)),
                "sources": sorted({item.source for item in items}),
                "impact_score": sum(severity_weight(item.severity) for item in items),
                "max_severity_weight": max(severity_weight(item.severity) for item in items),
                "first_seen": min(epochs) if epochs else None,
                "last_seen": max(epochs) if epochs else None,
            }
        )

    # Rank: worst severity, then impact, then earliest first_seen.
    clusters.sort(
        key=lambda c: (
            -c["max_severity_weight"],
            -c["impact_score"],
            c["first_seen"] if c["first_seen"] is not None else float("inf"),
        )
    )
    return clusters


def correlate(clusters: list[dict[str, Any]], window_seconds: int) -> list[dict[str, Any]]:
    """Tag clusters origin / correlated / separate against the time window."""
    starts = [c["first_seen"] for c in clusters if c["first_seen"] is not None]
    if not starts:
        for index, cluster in enumerate(clusters):
            cluster["correlation"] = "origin" if index == 0 else "correlated"
        return clusters

    incident_start = min(starts)
    for cluster in clusters:
        first_seen = cluster["first_seen"]
        if first_seen is None:
            cluster["correlation"] = "correlated"
            cluster["offset_seconds"] = None
            continue

        offset = first_seen - incident_start
        cluster["offset_seconds"] = round(offset, 3)
        if offset > window_seconds:
            cluster["correlation"] = "separate"
        elif offset <= 0:
            cluster["correlation"] = "origin"
        else:
            cluster["correlation"] = "correlated"
    return clusters


_SIGNALS: tuple[tuple[str, str], ...] = (
    (
        r"latency|slow|timeout|p9\d|deadline",
        "Latency is in the signal: check dependency response times and connection pool "
        "saturation before assuming the service itself is at fault.",
    ),
    (
        r"connection|pool|refus|reset|socket|econn",
        "Connection errors present: verify pool limits, keepalive settings, and whether a "
        "dependency is shedding load.",
    ),
    (
        r"\b5\d\d\b|error rate|exception|panic|crash",
        "Server-side errors present: compare the error signature against the most recent "
        "deploy and config change.",
    ),
    (
        r"cpu|memory|oom|disk|throttl|saturat|quota",
        "Resource pressure present: check limits and requests, recent traffic growth, and "
        "whether a rollback would restore headroom.",
    ),
    (
        r"cert|tls|ssl|expir|auth|jwt|token|forbidden|401|403",
        "Auth or certificate signals present: check expiry dates and credential rotation "
        "before debugging application logic.",
    ),
    (
        r"replica|lag|sync|quorum|split.?brain|failover|primary",
        "Replication signals present: confirm cluster quorum and replica lag before "
        "failing over.",
    ),
)


def draft_recommendations(clusters: list[dict[str, Any]]) -> list[str]:
    """Build next steps from the signals actually present in the alert text."""
    if not clusters:
        return ["No alerts available; confirm the alerting pipeline is delivering."]

    primary = clusters[0]
    service = primary.get("service", "unknown")
    corpus = " ".join(str(c.get("summary", "")) for c in clusters).lower()

    steps = [
        f"Start with {service}: review its dashboard, recent deploys, and SLO burn rate "
        f"over the alert window."
    ]
    steps += [advice for pattern, advice in _SIGNALS if re.search(pattern, corpus)]

    downstream = [
        c["service"] for c in clusters[1:] if c.get("correlation") == "correlated"
    ][:3]
    if downstream:
        steps.append(
            f"Treat {', '.join(downstream)} as possibly downstream of {service}; confirm "
            f"before paging those owners separately."
        )

    separate = [c["service"] for c in clusters if c.get("correlation") == "separate"]
    if separate:
        steps.append(
            f"{', '.join(separate)} began alerting outside the correlation window and may "
            f"be an unrelated incident."
        )

    steps.append(
        f"If {service} stays impaired, page the owning team, prepare a rollback, and record "
        f"mitigation steps in the incident channel."
    )
    return steps


def build_summary(clusters: list[dict[str, Any]], alerts: list[Alert]) -> str:
    if not clusters:
        return "No incident clusters available."

    primary = clusters[0]
    total = sum(cluster["alert_count"] for cluster in clusters)
    sources = sorted({alert.source for alert in alerts})
    text = (
        f"Incident detected across {len(clusters)} service cluster(s) from "
        f"{', '.join(sources)}. The highest-impact service is "
        f"{primary['service']}, with {total} alert(s) observed in total."
    )
    if primary.get("severities"):
        text += f" Severities on {primary['service']}: {', '.join(primary['severities'])}."
    return text


def analyze_incident(
    alerts: list[dict[str, Any]], llm_adapter: LLMAdapter | None = None
) -> IncidentAnalysis:
    settings = get_settings()
    logger.info("Starting incident analysis for %d alerts", len(alerts))

    normalized = [normalize_alert(alert) for alert in alerts]
    if not normalized:
        return IncidentAnalysis(
            clusters=[],
            summary="No alerts supplied.",
            recommendations=draft_recommendations([]),
        )

    clusters = correlate(
        build_clusters(normalized), settings.correlation_window_seconds
    )
    deterministic_summary = build_summary(clusters, normalized)
    recommendations = draft_recommendations(clusters)

    summary = deterministic_summary
    provider = "offline"
    if settings.enable_llm:
        adapter = llm_adapter or LLMAdapter(settings=settings)
        provider = adapter.provider
        summary = adapter.summarize(clusters, deterministic_summary)

    epochs = [item.epoch for item in normalized if item.epoch is not None]
    window = round(max(epochs) - min(epochs), 3) if len(epochs) > 1 else None

    logger.info(
        "Completed analysis: primary=%s clusters=%d provider=%s",
        clusters[0]["service"],
        len(clusters),
        provider,
    )
    return IncidentAnalysis(
        clusters=clusters,
        summary=summary,
        recommendations=recommendations,
        primary_service=clusters[0]["service"],
        alert_count=len(normalized),
        window_seconds=window,
        llm_provider=provider,
    )
