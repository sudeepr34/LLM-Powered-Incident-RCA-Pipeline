# Incident RCA Pipeline

Takes Prometheus / ELK alerts, groups them into service clusters, ranks the
clusters the way you'd triage on call, and drafts the first runbook steps.
Optionally sends the correlated structure to an LLM for a readable summary.

When something breaks you get twenty alerts from six services in a minute, and
most of them are the same failure from different angles. Sorting origin from
collateral is the slow part of the first five minutes.

## Behaviour

- **Severity over volume** — one `critical` outranks five `warning`s. Tie-break
  is which cluster started alerting first.
- **Correlation window** — clusters that start within
  `RCA_CORRELATION_WINDOW_SECONDS` (default 900) of the first alert are one
  incident. Anything later is tagged `separate`, not silently merged.
- **Advice from the alert text** — recommendations match signals that are
  actually present (latency, connection errors, 5xx, resource pressure,
  cert/auth, replication).
- **LLM is optional and never required** — timeout, HTTP error, bad JSON,
  empty response, or missing key all fall back to the deterministic summary.

## Example

`POST /api/ingest` with [`sample_alerts.json`](sample_alerts.json), then
`POST /api/analyze`:

```jsonc
{
  "summary": "Incident detected across 2 service cluster(s) from elk, prometheus. The highest-impact service is checkout, with 3 alert(s) observed in total. Severities on checkout: critical, warning.",
  "primary_service": "checkout",
  "alert_count": 3,
  "window_seconds": 120.0,
  "llm_provider": "offline",
  "clusters": [
    {
      "service": "checkout",
      "alert_count": 2,
      "severities": ["critical", "warning"],
      "summary": "latency spike; db connection pool saturation",
      "impact_score": 10,
      "offset_seconds": 0.0,
      "correlation": "origin"
    },
    {
      "service": "payments",
      "alert_count": 1,
      "severities": ["critical"],
      "summary": "payment gateway timeout",
      "offset_seconds": 120.0,
      "correlation": "correlated"
    }
  ],
  "recommendations": [
    "Start with checkout: review its dashboard, recent deploys, and SLO burn rate over the alert window.",
    "Latency is in the signal: check dependency response times and connection pool saturation before assuming the service itself is at fault.",
    "Treat payments as possibly downstream of checkout; confirm before paging those owners separately."
  ]
}
```

## LLM summary

Off by default. Enable with `RCA_ENABLE_LLM=true`:

| Provider | Endpoint | Notes |
| --- | --- | --- |
| `offline` | none | Default. No network. |
| `ollama` | `http://localhost:11434/api/chat` | Local model, no egress. |
| `openai` | `{RCA_LLM_BASE_URL}/chat/completions` | Any OpenAI-compatible API (OpenAI, Groq, vLLM, LM Studio, …). |

```bash
RCA_ENABLE_LLM=true RCA_LLM_PROVIDER=ollama RCA_LLM_MODEL=llama3.1 \
  python -m app.main --sample

RCA_ENABLE_LLM=true RCA_LLM_PROVIDER=openai \
  RCA_LLM_BASE_URL=http://vllm.internal:8000/v1 \
  RCA_LLM_API_KEY=... python -m app.main --sample
```

Retries with backoff for 408/429/5xx and transport errors. A 401 is not
retried.

Prompts are redacted before leaving the process (`RCA_LLM_REDACT=true`): IPs,
emails, AWS keys, JWTs, UUIDs, hashes, and `key=value` secrets. Key *names*
are kept so the model can still reason about "an auth token failed".

```
api_key=sk_live_abc123def456  ->  api_key=[SECRET]
timeout from 10.0.0.5         ->  timeout from [IP]
```

## API

```
GET  /api/health
GET  /api/config
POST /api/alerts
POST /api/ingest
POST /api/analyze
```

`/api/ingest` accepts Alertmanager, Elasticsearch (`hits.hits` / `_source`),
and plain lists. Timestamps: ISO 8601, epoch seconds, or milliseconds.

Guardrails: `extra="forbid"`, 100-item ingest cap (413), 404 from `/analyze`
when empty, field length limits.

## Run

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"

python -m app.main --sample
python -m app.main sample_alerts.json
python -m app.main --serve
pytest -q                    # 44 tests
```

```bash
./scripts/run-podman.sh      # SQLite volume
docker compose up --build    # API + Postgres (waits on pg_isready)
```

## Layout

```
app/analysis/rca.py           cluster / correlate / recommend
app/analysis/llm_adapter.py   offline / openai / ollama
app/analysis/redaction.py     prompt scrubbing
app/ingestion/normalize.py    Prometheus / ELK shapes
app/storage/                  SQLAlchemy store
app/http/                     FastAPI routes
app/core/                     settings + models
```

## Testing

44 tests, no network. LLM providers use an injected stub client that records
the outgoing request, so request shape and auth headers are pinned and every
failure path is covered. Live OpenAI/Ollama calls are not part of CI — the
`offline` path is what runs end to end locally.

## Limitations

- Clustering is by service name only — no dependency graph
- Advice is keyword-matched, not diagnosed
- No dedup of repeated firings of the same alert
- No auth; CORS is open for local use
- LLM summary is a draft — edit before it goes in a postmortem

## License

MIT — see [LICENSE](LICENSE).
