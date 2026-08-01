from __future__ import annotations

import json
from typing import Any

from sqlalchemy import Column, Integer, String
from sqlalchemy.orm import declarative_base

from app.storage.database import SessionLocal

Base = declarative_base()


class AlertStore:
    """SQLAlchemy-backed persistence for alerts and RCA analysis results."""

    def save_alert(self, alert: dict[str, Any]) -> dict[str, Any]:
        from app.storage.database import AlertRecord

        with SessionLocal() as session:
            record = AlertRecord(
                service=alert.get("service", "unknown"),
                severity=alert.get("severity", "warning"),
                summary=alert.get("summary", ""),
                timestamp=alert.get("timestamp", ""),
                source=alert.get("source", "unknown"),
            )
            session.add(record)
            session.commit()
            session.refresh(record)
            return {
                "id": record.id,
                "service": record.service,
                "severity": record.severity,
                "summary": record.summary,
                "timestamp": record.timestamp,
                "source": record.source,
            }

    def list_alerts(self) -> list[dict[str, Any]]:
        from app.storage.database import AlertRecord

        with SessionLocal() as session:
            records = session.query(AlertRecord).all()
            return [
                {
                    "id": record.id,
                    "service": record.service,
                    "severity": record.severity,
                    "summary": record.summary,
                    "timestamp": record.timestamp,
                    "source": record.source,
                }
                for record in records
            ]

    def save_rca(self, summary: str, clusters: list[dict[str, Any]], recommendations: list[str]) -> dict[str, Any]:
        from app.storage.database import RCARecord

        with SessionLocal() as session:
            record = RCARecord(
                summary=summary,
                clusters=json.dumps(clusters),
                recommendations=json.dumps(recommendations),
            )
            session.add(record)
            session.commit()
            session.refresh(record)
            return {"id": record.id, "summary": record.summary}
