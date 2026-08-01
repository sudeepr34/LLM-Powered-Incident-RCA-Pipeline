from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.analysis.rca import analyze_incident
from app.ingestion.normalize import normalize_payload
from app.storage.store import AlertStore

router = APIRouter(prefix="/api", tags=["incident-rca"])
store = AlertStore()


class AlertIn(BaseModel):
    service: str
    severity: str = Field(default="warning")
    summary: str
    timestamp: str = ""
    source: str = "unknown"


class IngestionPayload(BaseModel):
    payload: dict[str, Any] | list[dict[str, Any]]


@router.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@router.post("/alerts", summary="Store a single alert")
def ingest_alert(alert: AlertIn) -> dict[str, Any]:
    try:
        stored = store.save_alert(alert.model_dump())
    except Exception as exc:  # pragma: no cover - defensive
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    return {"status": "stored", "alert_id": stored["id"]}


@router.post("/ingest", summary="Ingest Prometheus or ELK-style payloads")
def ingest(payload: IngestionPayload) -> dict[str, Any]:
    try:
        normalized = normalize_payload(payload.payload)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    saved_ids = []
    for item in normalized:
        saved = store.save_alert(item)
        saved_ids.append(saved["id"])

    return {"status": "stored", "alert_ids": saved_ids}


@router.post("/analyze", summary="Run RCA analysis over stored alerts")
def analyze() -> dict[str, Any]:
    alerts = store.list_alerts()
    result = analyze_incident(alerts)
    return {
        "summary": result.summary,
        "clusters": result.clusters,
        "recommendations": result.recommendations,
    }
