from app.analysis.rca import analyze_incident, normalize_alert


def test_correlates_related_alerts_into_clusters():
    alerts = [
        {"service": "checkout", "severity": "critical", "summary": "latency spike", "timestamp": "2026-08-02T10:00:00Z", "source": "prometheus"},
        {"service": "checkout", "severity": "warning", "summary": "db connection pool saturation", "timestamp": "2026-08-02T10:01:00Z", "source": "elk"},
        {"service": "payments", "severity": "critical", "summary": "payment gateway timeout", "timestamp": "2026-08-02T10:02:00Z", "source": "prometheus"},
    ]

    result = analyze_incident(alerts)

    assert len(result["clusters"]) >= 2
    assert any(cluster["service"] == "checkout" for cluster in result["clusters"])
    assert result["summary"].lower().count("checkout") >= 1


def test_generates_runbook_recommendations():
    alerts = [
        {"service": "auth", "severity": "critical", "summary": "JWT validation failures", "timestamp": "2026-08-02T11:00:00Z", "source": "elk"},
    ]

    result = analyze_incident(alerts)

    assert result["recommendations"]
    assert any("auth" in recommendation.lower() for recommendation in result["recommendations"])


def test_normalizes_prometheus_and_elk_fields():
    alert = {
        "service_name": "inventory",
        "level": "error",
        "message": "cache miss storm",
        "@timestamp": "2026-08-02T12:00:00Z",
        "source": "elk",
    }

    normalized = normalize_alert(alert)

    assert normalized["service"] == "inventory"
    assert normalized["severity"] == "error"
    assert normalized["summary"] == "cache miss storm"
