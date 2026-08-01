from __future__ import annotations

from typing import Any


def _coerce_alert(payload: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(payload, dict):
        raise ValueError("Each alert payload must be an object")

    if "_source" in payload:
        payload = payload["_source"]

    if "service" in payload or "service_name" in payload or "summary" in payload or "message" in payload:
        return payload

    if "labels" in payload and isinstance(payload["labels"], dict):
        return payload

    raise ValueError("Unsupported alert payload shape")


def normalize_payload(payload: Any) -> list[dict[str, Any]]:
    """Normalize Prometheus and ELK-style payloads into alert dictionaries."""
    if isinstance(payload, list):
        return [_coerce_alert(item) for item in payload]

    if isinstance(payload, dict):
        if "alerts" in payload:
            return normalize_payload(payload["alerts"])

        if "prometheus" in payload:
            return normalize_payload(payload["prometheus"])

        if "hits" in payload and isinstance(payload["hits"], dict):
            hits = payload["hits"].get("hits", [])
            return normalize_payload(hits)

        if "data" in payload and isinstance(payload["data"], list):
            return normalize_payload(payload["data"])

        if "_source" in payload or "service" in payload or "service_name" in payload or "summary" in payload or "message" in payload:
            return [_coerce_alert(payload)]

    raise ValueError("Unsupported payload shape")
