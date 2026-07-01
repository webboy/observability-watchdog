# Observability Watchdog

This project is an **API-first Intelligent Observability & Event Watchdog MVP**. It ingests ECS-compatible JSONL application logs, stores normalized events in PostgreSQL, detects service-level error and latency anomalies using an explainable baseline scoring pipeline, creates simulated webhook alerts, and visualizes health trends through a Streamlit dashboard.

The system supports multiple monitored applications. Each application acts as an observability boundary, while individual services are extracted from the ECS `service.name` field.

The anomaly detection logic is isolated behind an `AnomalyDetectionService` so the detection strategy can evolve without changing ingestion, storage, alerting, or dashboard code.

**No paid cloud resources are used.** The project runs locally with Docker Compose.

---

## What This Project Is (and Is Not)

| In scope | Out of scope |
|---|---|
| Local API-first SRE watchdog | Production observability platform |
| ECS JSONL ingestion and validation | Real cloud log shipping |
| Explainable baseline anomaly detection | Black-box ML/LLM alert decisions |
| Simulated webhook alerts | Slack/PagerDuty delivery |
| Optional LLM incident summaries | Required paid LLM API keys |
| Streamlit dashboard over REST APIs | Multi-tenant SaaS deployment |

---

## Architecture At A Glance

```text
ECS JSONL -> LogEvent -> MetricWindow -> Anomaly -> Alert -> Dashboard
                              \-> Incident Summary (optional LLM)
```

For the full design, see [architecture.md](architecture.md).

---

## Prerequisites

- Python 3.12+
- Docker and Docker Compose
- Make (optional, recommended)

---

## Quick Start (Local Development)

```bash
cp .env.example .env
make install
make db
make migrate
make api          # terminal 1 — http://localhost:8000/docs
make dashboard    # terminal 2 — http://localhost:8501
```

On WSL/headless environments Streamlit does not auto-open a browser; open http://localhost:8501 manually.

---

## Docker Compose (API + Database)

Start the full stack with PostgreSQL and the FastAPI service:

```bash
cp .env.example .env
docker compose up --build
# or
make up
```

- API docs: http://localhost:8000/docs
- Health: http://localhost:8000/health and http://localhost:8000/api/v1/health

The dashboard still runs locally via `make dashboard` because it is a separate Streamlit client.

---

## Makefile Commands

```bash
make help              # list all targets
make install           # create .venv and install dependencies
make db                # start PostgreSQL container
make migrate           # run Alembic migrations
make api               # run FastAPI with auto-reload
make dashboard         # run Streamlit dashboard
make test              # run full pytest suite (uses watchdog_test DB)
make test-integration  # run end-to-end integration test only
make db-clear-data     # truncate dynamic tables, keep apps and rules
make up                # docker compose up --build
make down              # stop Docker Compose stack
```

---

## Demo Walkthrough

1. Start the API and database (`make db`, `make migrate`, `make api`).
2. Start the dashboard (`make dashboard`).
3. Create or select an app in the sidebar.
4. Click **Load Sample Incident Dataset** (uses `data/sample_incident_logs.jsonl`).
5. Wait for ingestion polling to complete (`status: completed`).
6. Review overview metrics, health trends, anomalies, alerts, and incident summary.
7. Use **Clear App Data** to reset the selected app without deleting it.

Sample datasets:

- `data/sample_logs.jsonl` — baseline traffic
- `data/sample_incident_logs.jsonl` — incident scenario with error/latency spikes

---

## Log Format (ECS-Compatible JSONL)

Logs are ingested as JSONL/NDJSON with ECS-compatible fields. The parser accepts both **flat dotted keys** and **nested JSON objects**.

### Required fields

| ECS field | Normalized column |
|---|---|
| `@timestamp` | `timestamp` (UTC-aware) |
| `log.level` | `log_level` |
| `message` | `message` |
| `service.name` | `service_name` |

### Optional fields

| ECS field | Normalized column |
|---|---|
| `event.id` | `event_id` |
| `event.dataset` | `event_dataset` |
| `event.outcome` | `event_outcome` |
| `event.duration` | `event_duration_ns` |
| `http.response.status_code` | `http_status_code` |
| `url.path` | `url_path` |
| `trace.id` | `trace_id` |
| `span.id` | `span_id` |
| `transaction.id` | `transaction_id` |
| `error.type` | `error_type` |
| `error.message` | `error_message` |

The full raw event is stored in `log_events.raw_event_json` (PostgreSQL JSONB).

### Example event

```json
{
  "@timestamp": "2026-06-30T12:01:00Z",
  "log.level": "ERROR",
  "message": "Payment timeout",
  "service.name": "payment-service",
  "http.response.status_code": 502,
  "url.path": "/payments/charge",
  "error.type": "UpstreamTimeout"
}
```

---

## Data Pipeline

### 1. Ingestion (`LogEvent`)

- Upload JSONL, batch JSON, or validate-only dry run.
- Parser normalizes ECS fields and rejects invalid events.
- Deduplication uses app-scoped `event.id` when present, otherwise SHA-256 of canonical normalized fields.
- PostgreSQL `ON CONFLICT DO NOTHING` on `(app_id, dedupe_key)` skips duplicates.
- Ingestion returns `status: processing` when new events are accepted.

### 2. Background post-processing

After ingestion, FastAPI `BackgroundTasks` runs:

1. Metric aggregation into fixed 10-minute buckets
2. Baseline anomaly detection
3. Optional incident summary enrichment
4. Simulated alert creation

Poll `GET /api/v1/apps/{app_id}/ingestion-runs/{run_id}` until `completed`.

### 3. Metric aggregation (`MetricWindow`)

Raw events are aggregated into fixed **10-minute windows** scoped by:

- `app_id`
- `service_name`
- `url_path`

Computed metrics per window:

- `total_events`, `error_count`, `error_rate`
- `http_5xx_count`, `http_5xx_rate`
- `latency_p95_ms` (from `event.duration` nanoseconds)
- `unique_error_types`, `most_common_error_type`

Overlapping uploads recompute affected buckets from all raw events (no duplicate windows).

### 4. Anomaly detection (explainable, not black-box)

Detection is rule-based and deterministic. **LLMs do not decide whether an anomaly exists.**

For each metric window, the service:

1. Resolves an app-specific rule, or falls back to a global default
2. Computes baseline as the average of up to **six prior 10-minute windows** within the previous **60 minutes** relative to `window_start`
3. Floors zero/missing baselines to `1.0` (cold-start guard)
4. Calculates `anomaly_score = observed_value / baseline_value`
5. Classifies severity:
   - `WARNING` when score >= warning multiplier
   - `CRITICAL` when score >= critical multiplier
6. Suppresses low-volume windows below `min_event_count`
7. Removes stale anomalies when metrics return to normal

Default global rules:

| Metric | Warning | Critical | Min events |
|---|---|---|---|
| `error_count` | 3.0x | 8.0x | 10 |
| `http_5xx_rate` | 2.0x | 5.0x | 20 |
| `latency_p95` | 2.0x | 4.0x | 20 |

### 5. Alerts and incident intelligence

- **Alerts**: simulated webhook payloads persisted from WARNING/CRITICAL anomalies (idempotent per `anomaly_id`).
- **Incident summaries**: optional Gemini/OpenAI enrichment with deterministic template fallback when no API key is configured.

**Important:** The LLM is used only in the incident intelligence layer to summarize detected anomalies, infer likely business impact, and suggest remediation. It is not the source of truth for anomaly decisions.

### 6. Health score (relative time semantics)

```text
health_score = max(0, 100 - 25 × critical_count - 10 × warning_count)
```

The 24-hour scoring window is anchored to `MAX(log_events.timestamp)` for the selected app, **not** server wall-clock time.

---

## LLM Integration (Optional)

Configure in `.env`:

```text
LLM_PROVIDER=template
GEMINI_API_KEY=
OPENAI_API_KEY=
```

| Provider | Behavior |
|---|---|
| `template` (default) | Deterministic summaries, no API key required |
| `gemini` | Uses Gemini when `GEMINI_API_KEY` is set |
| `openai` | Uses OpenAI when `OPENAI_API_KEY` is set |

The project runs fully without any paid LLM API key.

---

## API Endpoints

### Apps and ingestion

- `POST /api/v1/apps` — create monitored app
- `GET /api/v1/apps` — list apps
- `GET /api/v1/apps/{app_id}` — get app
- `DELETE /api/v1/apps/{app_id}` — delete app
- `POST /api/v1/apps/{app_id}/logs/upload` — upload ECS JSONL file
- `POST /api/v1/apps/{app_id}/logs/events` — ingest JSON event batch
- `POST /api/v1/apps/{app_id}/logs/validate` — dry-run validation
- `GET /api/v1/apps/{app_id}/ingestion-runs/{ingestion_run_id}` — poll ingestion status

### Alerts and incidents

- `GET /api/v1/apps/{app_id}/alerts` — list simulated webhook alerts
- `GET /api/v1/apps/{app_id}/incidents/summary` — latest enriched incident summaries

### Dashboard

- `GET /api/v1/apps/{app_id}/dashboard/overview`
- `GET /api/v1/apps/{app_id}/dashboard/metric-windows`
- `GET /api/v1/apps/{app_id}/dashboard/top-failing-services`
- `GET /api/v1/apps/{app_id}/dashboard/anomalies`
- `POST /api/v1/apps/{app_id}/demo/load-sample-dataset`
- `POST /api/v1/apps/{app_id}/demo/clear-data`

---

## Automated Tests

```bash
make test
```

This runs:

1. `make db-test` — creates `watchdog_test` database if missing
2. `make test-migrate` — applies Alembic migrations to the test DB
3. `pytest` — 92+ tests against the isolated test database

Tests refuse to truncate non-test databases unless `ALLOW_DEV_DB_TESTS=1` is set.

```bash
make test-integration   # end-to-end MVP flow only
```

---

## Cloud Resources And Cost

| Resource | Used? |
|---|---|
| Paid cloud database | No — local PostgreSQL via Docker Compose |
| Paid cloud compute | No — local FastAPI and Streamlit |
| Paid LLM API keys | Optional — template fallback works without keys |
| Cloud decommissioning required | No — everything runs locally |

---

## Project Structure

```text
app/                  FastAPI application (API, services, repositories, models)
dashboard/            Streamlit client (calls API only)
data/                 Sample ECS JSONL datasets
migrations/           Alembic schema migrations
tests/                Pytest suite
architecture.md       System design document
presentation.md       Markdown slide deck
prompts.md            AI audit log (all prompts used during development)
```

---

## Final Submission Checklist

- [x] Complete source code in public GitHub repository
- [x] `prompts.md` with full AI audit log
- [x] README with setup and demo instructions
- [x] Architecture document (`architecture.md`)
- [x] AI-generated presentation deck (`presentation.md`)
- [x] Sample ECS-compatible JSONL logs (`data/sample_logs.jsonl`, `data/sample_incident_logs.jsonl`)
- [x] Dashboard available locally (`make dashboard`)
- [x] API docs available locally (`http://localhost:8000/docs`)
- [ ] Tagle.ai result summary (submit separately as required by assignment)
- [x] No paid cloud resources used
- [x] No cloud resources need decommissioning

---

## Further Reading

- [architecture.md](architecture.md) — data flow, schema, deduplication, async model
- [presentation.md](presentation.md) — slide deck for demo/review
- [project_brief_observability_watchdog.md](project_brief_observability_watchdog.md) — original assignment brief
