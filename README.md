# LLM-Powered Incident RCA Pipeline

This workspace contains a production-oriented MVP for an incident RCA pipeline. It correlates alerts from Prometheus and ELK-style sources, normalizes them into a consistent schema, clusters related incidents, and generates draft runbook recommendations for on-call engineers.

## Architecture

- Ingestion layer: accepts alert payloads from Prometheus and ELK-like sources
- Normalization layer: converts service, severity, and summary fields into a common shape
- Correlation layer: groups alerts by service and highlights the highest-impact cluster
- Summarization layer: emits a structured incident summary and draft recommendations
- Extension layer: supports future integration with an external LLM provider through a pluggable adapter

## Configuration

You can tune runtime behavior through environment variables such as:

- RCA_LOG_LEVEL
- RCA_DEFAULT_SOURCE
- RCA_ENABLE_LLM
- RCA_LLM_PROVIDER
- RCA_LLM_MODEL
- RCA_LLM_API_KEY
- RCA_DB_PASSWORD
- RCA_DATABASE_URL

For local development, place sensitive values in a separate .env file and keep it out of source control. The app will load it automatically.

## Guardrails and operational safety

The application now includes several guardrails to make it safer for real use:

- Input validation: alert payloads reject empty service names, excessive lengths, and unexpected fields.
- Oversized ingestion protection: bulk ingestion rejects payloads larger than 100 items with HTTP 413.
- Empty analysis protection: RCA analysis returns HTTP 404 when there are no stored alerts to analyze.
- Structured logging: key API events and errors are logged with context for easier troubleshooting.
- CORS middleware: the API is prepared for browser-based clients while still being restricted by default.

## Detailed documentation by section

### 1. Ingestion layer
The ingestion layer accepts either a single alert or a Prometheus/ELK-style payload and normalizes it into a common shape before persistence.

### 2. Analysis layer
The analysis layer groups alerts by service, builds a summary, and drafts recommendations. It can later be extended with an external LLM provider when enabled.

### 3. Storage layer
The storage layer persists alerts and RCA outputs in a SQLite database by default, but it can be pointed to another database using RCA_DATABASE_URL.

### 4. HTTP API
The HTTP API exposes health checks, alert ingestion, bulk ingestion, and RCA analysis. Each route is validated and guarded with operational safety checks.

### 5. Configuration and secrets
All runtime behavior is driven by environment variables. Sensitive values should be placed in a .env file or injected by your deployment platform.

## Quick start

```bash
python3 -m app.main --sample
python3 -m app.main sample_alerts.json
python3 -m app.main --serve
```

## Containerization

This environment uses Podman rather than Docker Compose, so the recommended startup command is:

```bash
./scripts/run-podman.sh
```

Then use:

- http://localhost:8000/health
- POST http://localhost:8000/alerts
- POST http://localhost:8000/analyze

## What it does

- Ingests alert payloads from Prometheus/ELK-like sources
- Groups related alerts into service clusters
- Produces a human-readable RCA summary
- Drafts actionable runbook recommendations
- Supports structured logging and extension points for future production integration

## Verification

The implementation has been exercised directly with Python and produced a valid RCA summary, cluster output, and recommendation list.
