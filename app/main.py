from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path
from typing import Any

from app.core.config import get_settings

import uvicorn

from app.http.app import app as api_app
from app.analysis.rca import analyze_incident

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger(__name__)
settings = get_settings()


def load_alerts(path: str | None = None) -> list[dict[str, Any]]:
    if path:
        with Path(path).open("r", encoding="utf-8") as handle:
            payload = json.load(handle)
    else:
        payload = json.load(sys.stdin)

    if isinstance(payload, dict):
        payload = payload.get("alerts", [])
    if not isinstance(payload, list):
        raise ValueError("Input JSON must be a list of alerts or an object containing an 'alerts' list")
    return payload


def main() -> None:
    parser = argparse.ArgumentParser(description="Analyze incident alerts and generate RCA guidance")
    parser.add_argument("path", nargs="?", help="Optional path to a JSON file with alerts")
    parser.add_argument("--sample", action="store_true", help="Run with built-in sample data")
    parser.add_argument("--serve", action="store_true", help="Run the FastAPI service")
    args = parser.parse_args()

    logger.info("Starting RCA app with log_level=%s", settings.log_level)
    if args.serve or not any([args.sample, args.path]):
        uvicorn.run(api_app, host="0.0.0.0", port=8000)
        return

    alerts = []
    if args.sample:
        alerts = [
            {"service": "checkout", "severity": "critical", "summary": "latency spike", "timestamp": "2026-08-02T10:00:00Z", "source": "prometheus"},
            {"service": "checkout", "severity": "warning", "summary": "db connection pool saturation", "timestamp": "2026-08-02T10:01:00Z", "source": "elk"},
            {"service": "payments", "severity": "critical", "summary": "payment gateway timeout", "timestamp": "2026-08-02T10:02:00Z", "source": "prometheus"},
        ]
    else:
        alerts = load_alerts(args.path)

    logger.info("Analyzing %d alerts", len(alerts))
    result = analyze_incident(alerts)
    print(result.summary)
    print("Clusters:")
    for cluster in result.clusters:
        print(f"- {cluster['service']}: {cluster['alert_count']} alerts")
    print("Recommendations:")
    for item in result.recommendations:
        print(f"- {item}")


if __name__ == "__main__":
    main()
