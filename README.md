# Observability Watchdog

API-first Intelligent Observability & Event Watchdog MVP.

## Phase 1 Status

- FastAPI application skeleton
- PostgreSQL via Docker Compose
- SQLAlchemy models: `App`, `IngestionRun`, `LogEvent`
- Alembic migration for core tables
- Health endpoints: `/health`, `/api/v1/health`

## Phase 2 Status

- ECS-compatible JSONL/JSON parser with dotted and nested field support
- SHA-256 dedupe keys with PostgreSQL `ON CONFLICT DO NOTHING`
- Request-time log ingestion (upload, batch, validate)
- App CRUD endpoints

## Phase 3 Status

- FastAPI `BackgroundTasks` post-processing after ingestion
- Fixed 10-minute `MetricWindow` aggregation from raw log events
- Baseline anomaly detection with global/app rule inheritance
- Ingestion run polling endpoint for async completion

## Phase 4 Status

- Simulated webhook alerts persisted from WARNING/CRITICAL anomalies
- Idempotent alert creation keyed by `anomaly_id`
- Incident summary enrichment with Gemini/OpenAI optional providers and template fallback
- Alert listing and incident summary API endpoints

## Phase 5 Status

- Streamlit dashboard client (`dashboard/streamlit_app.py`) using FastAPI endpoints only
- App selector, ingestion controls, async polling, overview metrics, and health trends
- Plotly charts for errors, HTTP 5xx rate, and p95 latency
- Top failing services, anomalies/alerts tables, and incident summary panel
- Demo endpoints: `POST /api/v1/apps/{app_id}/demo/load-sample-dataset`, `POST /api/v1/apps/{app_id}/demo/clear-data`

## Quick Start

```bash
cp .env.example .env
docker compose up -d db
pip install -r requirements.txt
alembic upgrade head
uvicorn app.main:app --reload
```

API docs: http://localhost:8000/docs

## Health Checks

- `GET /health` — basic app health
- `GET /api/v1/health` — app health with database connectivity

## App And Ingestion API

- `POST /api/v1/apps` — create monitored app
- `GET /api/v1/apps` — list apps
- `GET /api/v1/apps/{app_id}` — get app
- `DELETE /api/v1/apps/{app_id}` — delete app
- `POST /api/v1/apps/{app_id}/logs/upload` — upload ECS JSONL file
- `POST /api/v1/apps/{app_id}/logs/events` — ingest JSON event batch
- `POST /api/v1/apps/{app_id}/logs/validate` — dry-run validation
- `GET /api/v1/apps/{app_id}/ingestion-runs/{ingestion_run_id}` — poll ingestion status

Ingestion with new events returns `status: processing`; poll the ingestion-run endpoint until `completed`.

## Alerts And Incident Intelligence

- `GET /api/v1/apps/{app_id}/alerts` — list simulated webhook alerts
- `GET /api/v1/apps/{app_id}/incidents/summary` — latest enriched incident summaries

Optional LLM settings in `.env`:

```text
LLM_PROVIDER=template
GEMINI_API_KEY=
OPENAI_API_KEY=
```

When no API key is configured, deterministic template summaries are used.

```bash
curl http://localhost:8000/api/v1/apps/<app_id>/alerts
curl http://localhost:8000/api/v1/apps/<app_id>/incidents/summary
```

## Dashboard

Start the API and database first, then launch the Streamlit dashboard:

```bash
make db
make migrate
make api
make dashboard
```

Dashboard URL: http://localhost:8501

Recommended demo flow:

1. Create or select an app in the sidebar.
2. Click **Load Sample Incident Dataset**.
3. Wait for ingestion polling to complete.
4. Review overview metrics, health trends, anomalies, alerts, and incident summary.
5. Use **Clear App Data** to reset the selected app without deleting it.

Dashboard API endpoints:

- `GET /api/v1/apps/{app_id}/dashboard/overview`
- `GET /api/v1/apps/{app_id}/dashboard/metric-windows`
- `GET /api/v1/apps/{app_id}/dashboard/top-failing-services`
- `GET /api/v1/apps/{app_id}/dashboard/anomalies`
- `POST /api/v1/apps/{app_id}/demo/load-sample-dataset`
- `POST /api/v1/apps/{app_id}/demo/clear-data`

## App And Ingestion Examples

```bash
curl -X POST http://localhost:8000/api/v1/apps \
  -H 'Content-Type: application/json' \
  -d '{"name":"E-commerce Platform","slug":"ecommerce-platform","environment":"production"}'

curl -X POST http://localhost:8000/api/v1/apps/<app_id>/logs/events \
  -H 'Content-Type: application/json' \
  -d '{"events":[{"@timestamp":"2026-06-30T12:01:00Z","log.level":"ERROR","message":"Payment timeout","service.name":"payment-service"}]}'
```

## Development

```bash
make help
make install
make db
make migrate
make api
make dashboard
make test
```

Or use the full Docker Compose stack:

```bash
make up
```

See `make help` for all available targets including the Streamlit dashboard (`make dashboard`, Phase 5).
