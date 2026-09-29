from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field, ConfigDict

from app.analysis.rca import analyze_incident
from app.core.config import get_settings
from app.ingestion.normalize import normalize_payload
from app.storage.store import AlertStore

router = APIRouter(prefix="/api", tags=["incident-rca"])
store = AlertStore()
logger = logging.getLogger(__name__)


class AlertIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    service: str = Field(min_length=1, max_length=100)
    severity: str = Field(default="warning", min_length=1, max_length=20)
    summary: str = Field(min_length=1, max_length=500)
    timestamp: str = Field(default="", max_length=100)
    source: str = Field(default="unknown", min_length=1, max_length=100)


class IngestionPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    payload: dict[str, Any] | list[dict[str, Any]]


@router.get("/health")
def health() -> dict[str, str]:
    logger.info("Health check requested")
    return {"status": "ok"}


@router.post("/alerts", summary="Store a single alert")
def ingest_alert(alert: AlertIn) -> dict[str, Any]:
    logger.info("Storing alert for service=%s severity=%s", alert.service, alert.severity)
    try:
        stored = store.save_alert(alert.model_dump())
    except Exception as exc:  # pragma: no cover - defensive
        logger.exception("Failed to persist alert")
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    return {"status": "stored", "alert_id": stored["id"]}


@router.post("/ingest", summary="Ingest Prometheus or ELK-style payloads")
def ingest(payload: IngestionPayload) -> dict[str, Any]:
    if isinstance(payload.payload, list) and len(payload.payload) > 100:
        logger.warning("Rejected oversized payload with %d items", len(payload.payload))
        raise HTTPException(status_code=413, detail="Payload contains too many items")

    try:
        normalized = normalize_payload(payload.payload)
    except ValueError as exc:
        logger.warning("Invalid ingestion payload: %s", exc)
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    saved_ids = []
    for item in normalized:
        saved = store.save_alert(item)
        saved_ids.append(saved["id"])

    logger.info("Stored %d normalized alerts", len(saved_ids))
    return {"status": "stored", "alert_ids": saved_ids}


@router.post("/analyze", summary="Run RCA analysis over stored alerts")
def analyze() -> dict[str, Any]:
    logger.info("Starting RCA analysis over stored alerts")
    alerts = store.list_alerts()
    if not alerts:
        logger.warning("No alerts available for RCA analysis")
        raise HTTPException(status_code=404, detail="No alerts available for analysis")

    result = analyze_incident(alerts)
    store.save_rca(result.summary, result.clusters, result.recommendations)
    logger.info("Completed RCA analysis with %d clusters", len(result.clusters))
    return {
        "summary": result.summary,
        "primary_service": result.primary_service,
        "alert_count": result.alert_count,
        "window_seconds": result.window_seconds,
        "llm_provider": result.llm_provider,
        "clusters": result.clusters,
        "recommendations": result.recommendations,
    }


@router.get("/config", summary="Report the active analysis configuration")
def config() -> dict[str, Any]:
    """Which summariser is live, without exposing the API key."""
    settings = get_settings()
    return {
        "llm_enabled": settings.enable_llm,
        "llm_provider": settings.llm_provider if settings.enable_llm else "offline",
        "llm_model": settings.llm_model,
        "llm_redaction": settings.llm_redact,
        "api_key_configured": bool(settings.llm_api_key),
        "correlation_window_seconds": settings.correlation_window_seconds,
    }
