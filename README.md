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

Example:

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
make test
```

Or use the full Docker Compose stack:

```bash
make up
```

See `make help` for all available targets including the Streamlit dashboard (`make dashboard`, Phase 5).
