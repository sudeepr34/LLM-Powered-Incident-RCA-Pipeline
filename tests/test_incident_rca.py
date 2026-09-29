from __future__ import annotations

from app.analysis.rca import (
    analyze_incident,
    build_clusters,
    correlate,
    normalize_alert,
    parse_timestamp,
)


def test_correlates_related_alerts_into_clusters():
    alerts = [
        {"service": "checkout", "severity": "critical", "summary": "latency spike", "timestamp": "2026-08-02T10:00:00Z", "source": "prometheus"},
        {"service": "checkout", "severity": "warning", "summary": "db connection pool saturation", "timestamp": "2026-08-02T10:01:00Z", "source": "elk"},
        {"service": "payments", "severity": "critical", "summary": "payment gateway timeout", "timestamp": "2026-08-02T10:02:00Z", "source": "prometheus"},
    ]

    result = analyze_incident(alerts)

    assert len(result.clusters) == 2
    assert {c["service"] for c in result.clusters} == {"checkout", "payments"}
    assert "checkout" in result.summary.lower()
    assert result.alert_count == 3
    assert result.window_seconds == 120.0


def test_generates_runbook_recommendations():
    alerts = [
        {"service": "auth", "severity": "critical", "summary": "JWT validation failures", "timestamp": "2026-08-02T11:00:00Z", "source": "elk"},
    ]

    result = analyze_incident(alerts)

    assert result.recommendations
    assert any("auth" in step.lower() for step in result.recommendations)
    # The auth/token signal should surface the credential-specific advice.
    assert any("certificate" in step.lower() for step in result.recommendations)


def test_recommendations_follow_the_observed_signals():
    """Advice is keyed off alert text, so resource alerts get resource advice."""
    alerts = [
        {"service": "ledger", "severity": "critical", "summary": "container OOMKilled, memory limit exceeded", "timestamp": "2026-08-02T11:00:00Z"},
    ]

    steps = " ".join(analyze_incident(alerts).recommendations).lower()

    assert "resource pressure" in steps
    assert "certificate" not in steps


def test_normalizes_prometheus_and_elk_fields():
    alert = {
        "service_name": "inventory",
        "level": "error",
        "message": "cache miss storm",
        "@timestamp": "2026-08-02T12:00:00Z",
        "source": "elk",
    }

    normalized = normalize_alert(alert)

    assert normalized.service == "inventory"
    assert normalized.severity == "error"
    assert normalized.summary == "cache miss storm"
    assert normalized.epoch is not None


def test_normalizes_alertmanager_label_shape():
    alert = {
        "labels": {"service": "gateway", "severity": "critical", "alertname": "HighErrorRate"},
        "annotations": {"summary": "5xx rate above 5%"},
        "startsAt": "2026-08-02T12:00:00Z",
    }

    normalized = normalize_alert(alert)

    assert normalized.service == "gateway"
    assert normalized.severity == "critical"
    assert normalized.summary == "5xx rate above 5%"


def test_severity_outranks_volume_when_ordering_clusters():
    """One critical must beat five warnings, or triage order is wrong."""
    alerts = [normalize_alert({"service": "noisy", "severity": "warning", "summary": "flapping", "timestamp": "2026-08-02T10:00:00Z"}) for _ in range(5)]
    alerts.append(
        normalize_alert(
            {"service": "database", "severity": "critical", "summary": "primary unreachable", "timestamp": "2026-08-02T10:00:30Z"}
        )
    )

    clusters = build_clusters(alerts)

    assert clusters[0]["service"] == "database"
    assert clusters[0]["alert_count"] == 1


def test_correlation_flags_late_clusters_as_separate():
    alerts = [
        normalize_alert({"service": "api", "severity": "critical", "summary": "down", "timestamp": "2026-08-02T10:00:00Z"}),
        normalize_alert({"service": "batch", "severity": "critical", "summary": "down", "timestamp": "2026-08-02T14:00:00Z"}),
    ]

    clusters = correlate(build_clusters(alerts), window_seconds=900)
    by_service = {c["service"]: c for c in clusters}

    assert by_service["api"]["correlation"] == "origin"
    assert by_service["batch"]["correlation"] == "separate"
    assert by_service["batch"]["offset_seconds"] == 14400.0


def test_correlation_marks_close_clusters_as_correlated():
    alerts = [
        normalize_alert({"service": "api", "severity": "critical", "summary": "down", "timestamp": "2026-08-02T10:00:00Z"}),
        normalize_alert({"service": "web", "severity": "critical", "summary": "down", "timestamp": "2026-08-02T10:01:00Z"}),
    ]

    clusters = correlate(build_clusters(alerts), window_seconds=900)
    by_service = {c["service"]: c for c in clusters}

    assert by_service["api"]["correlation"] == "origin"
    assert by_service["web"]["correlation"] == "correlated"


def test_analysis_of_no_alerts_is_not_an_error():
    result = analyze_incident([])

    assert result.clusters == []
    assert result.recommendations


def test_parse_timestamp_handles_the_common_formats():
    iso = parse_timestamp("2026-08-02T10:00:00Z")
    assert iso is not None
    assert parse_timestamp("1754128800") == 1754128800.0
    # Milliseconds are detected by magnitude and scaled down.
    assert parse_timestamp("1754128800000") == 1754128800.0
    assert parse_timestamp("not a timestamp") is None
    assert parse_timestamp("") is None


def test_clusters_without_timestamps_still_rank():
    alerts = [
        normalize_alert({"service": "a", "severity": "critical", "summary": "x"}),
        normalize_alert({"service": "b", "severity": "warning", "summary": "y"}),
    ]

    clusters = correlate(build_clusters(alerts), window_seconds=900)

    assert clusters[0]["service"] == "a"
    assert clusters[0]["correlation"] == "origin"
