from __future__ import annotations

from app.analysis.redaction import redact, redact_clusters


def test_redacts_ipv4_with_and_without_port():
    assert redact("upstream 10.4.2.9 refused") == "upstream [IP] refused"
    assert redact("upstream 10.4.2.9:8080 refused") == "upstream [IP] refused"


def test_redacts_email_addresses():
    assert redact("paged sudeep.reddy@example.com") == "paged [EMAIL]"


def test_redacts_aws_access_keys():
    assert "[AWS_KEY]" in redact("key AKIAIOSFODNN7EXAMPLE leaked")


def test_redacts_jwts():
    token = "eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxMjM0NTY3ODkwIn0.dBjftJeZ4CVPmB92K27uhbUJU1p1r"
    assert "[JWT]" in redact(f"auth failed for {token}")


def test_keeps_the_key_name_but_drops_the_secret_value():
    """The summary should still say what kind of credential failed."""
    result = redact("api_key=sk_live_abc123def456ghi789 rejected")

    assert "api_key" in result
    assert "sk_live_abc123def456ghi789" not in result
    assert "[SECRET]" in result


def test_redacts_uuids_and_long_hashes():
    assert "[UUID]" in redact("trace 123e4567-e89b-12d3-a456-426614174000")
    assert "[HASH]" in redact("digest d41d8cd98f00b204e9800998ecf8427e")


def test_leaves_ordinary_alert_text_alone():
    text = "checkout p99 latency above 500ms for 5 minutes"

    assert redact(text) == text


def test_handles_empty_input():
    assert redact("") == ""


def test_redact_clusters_scrubs_text_but_preserves_structure():
    clusters = [
        {"service": "checkout", "alert_count": 3, "summary": "timeout from 10.0.0.5"}
    ]

    result = redact_clusters(clusters)

    assert result[0]["alert_count"] == 3
    assert result[0]["summary"] == "timeout from [IP]"
    # The input must not be mutated in place.
    assert clusters[0]["summary"] == "timeout from 10.0.0.5"
