from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any


class AlertStore:
    """A simple JSON-file-backed alert store for local development and container demos."""

    def __init__(self, path: str | None = None) -> None:
        self.path = Path(path or os.getenv("RCA_ALERT_STORE_PATH", "/tmp/incident_alerts.json"))
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if not self.path.exists():
            self.path.write_text("[]", encoding="utf-8")

    def _load(self) -> list[dict[str, Any]]:
        return json.loads(self.path.read_text(encoding="utf-8"))

    def save_alert(self, alert: dict[str, Any]) -> dict[str, Any]:
        alerts = self._load()
        alert_record = {"id": len(alerts) + 1, **alert}
        alerts.append(alert_record)
        self.path.write_text(json.dumps(alerts, indent=2), encoding="utf-8")
        return alert_record

    def list_alerts(self) -> list[dict[str, Any]]:
        return self._load()
