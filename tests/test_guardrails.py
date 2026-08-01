from __future__ import annotations

from fastapi.testclient import TestClient

from app.http.app import app

client = TestClient(app)


def test_invalid_alert_is_rejected() -> None:
    response = client.post(
        "/api/alerts",
        json={"service": "", "severity": "fatal", "summary": "bad"},
    )

    assert response.status_code == 422


def test_oversized_ingest_is_rejected() -> None:
    payload = {
        "payload": [
            {"service": f"svc-{index}", "severity": "warning", "summary": "hello"}
            for index in range(101)
        ]
    }

    response = client.post("/api/ingest", json=payload)

    assert response.status_code == 413
