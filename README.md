# Observability Watchdog

API-first Intelligent Observability & Event Watchdog MVP.

## Phase 1 Status

- FastAPI application skeleton
- PostgreSQL via Docker Compose
- SQLAlchemy models: `App`, `IngestionRun`, `LogEvent`
- Alembic migration for core tables
- Health endpoints: `/health`, `/api/v1/health`

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
