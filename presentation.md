# Observability Watchdog

**API-first Intelligent Observability & Event Watchdog MVP**

Local SRE watchdog for ECS log ingestion, explainable anomaly detection, and incident intelligence.

---

# Project Context

- Hiring-challenge MVP: demonstrate architecture, API design, and AI-assisted development workflow
- Ingest ECS-compatible JSONL application logs
- Detect service-level error and latency anomalies
- Visualize health trends and incident intelligence
- Runs entirely on local Docker Compose — no paid cloud resources

**Goal:** Practical SRE observability patterns, not a production platform.

---

# SRE Positioning Statement

> An API-first watchdog that turns application logs into actionable observability signals — with explainable baselines, not black-box alerting.

| Layer | Responsibility |
|---|---|
| Ingestion | Parse, validate, dedupe ECS logs |
| Aggregation | Fixed 10-minute metric windows |
| Detection | Rule-based baseline spike scoring |
| Alerting | Simulated webhook alerts |
| Intelligence | Optional LLM incident summaries |
| Dashboard | Streamlit over REST APIs |

---

# Architecture Overview

```text
ECS JSONL  →  LogEvent  →  MetricWindow  →  Anomaly  →  Alert
                  │              │              │
                  │              └──── Dashboard ─┘
                  │                     │
                  └──── Incident Summary (optional LLM)
```

**Key principle:** Detection is deterministic. LLM enriches summaries downstream only.

---

# Data Flow Detail

1. **Upload** — JSONL file or JSON batch via FastAPI
2. **Parse** — ECS field normalization (dotted + nested keys)
3. **Dedupe** — app-scoped event.id or SHA-256 fallback
4. **Store** — PostgreSQL with JSONB raw payloads
5. **Aggregate** — 10-minute MetricWindow buckets
6. **Detect** — baseline anomaly scoring with configurable rules
7. **Alert** — simulated webhook payloads (idempotent)
8. **Summarize** — template or optional LLM enrichment
9. **Visualize** — Streamlit dashboard polls API endpoints

---

# Key Decision: PostgreSQL + JSONB

**Why not SQLite?**
- Production-grade indexes (GIN on JSONB, composite uniqueness)
- `ON CONFLICT DO NOTHING` for deduplication at scale
- Percentile aggregation (p95 latency) via SQL
- Signals backend architecture maturity

**Why not a paid cloud DB?**
- Assignment requires free/local infrastructure
- Reviewers can run `docker compose up` without credentials
- No decommissioning needed after evaluation

---

# Key Decision: ECS-Compatible Log Format

- Industry-standard field naming (`@timestamp`, `service.name`, `log.level`)
- Supports flat dotted keys AND nested JSON objects
- App boundary from API registration; service boundary from `service.name`
- Raw event preserved in JSONB for audit and future field extraction

```json
{"@timestamp":"2026-06-30T12:01:00Z","log.level":"ERROR",
 "message":"Payment timeout","service.name":"payment-service"}
```

---

# Key Decision: FastAPI BackgroundTasks

**Chosen:** In-process background tasks after ingestion response

**Rejected:** Celery + Redis for MVP

| BackgroundTasks | Celery |
|---|---|
| Zero extra infrastructure | Requires broker + workers |
| Reviewer-friendly `make api` | More setup for evaluators |
| Sufficient for JSONL uploads | Better for high-volume streaming |

**Future path:** Celery/RQ/Kafka when durability and horizontal scaling are required.

---

# Key Decision: Explainable Baselines

**Not black-box LLM alerting.**

```text
anomaly_score = observed_value / baseline_value
```

- Baseline = avg of 6 prior 10-min windows (60 min lookback)
- Cold-start floor: baseline minimum of 1.0
- WARNING at 3x, CRITICAL at 8x (error_count defaults)
- Volume suppression via min_event_count
- Stale anomaly cleanup when metrics normalize

Every anomaly includes: observed, baseline, score, and human-readable reason.

---

# Key Decision: Relative Time Semantics

Health scores and baselines anchor to **log timestamps**, not server clock:

- Baseline window: 60 min before metric `window_start`
- Health score window: 24h before `MAX(log_events.timestamp)`
- Metric buckets: fixed 10-min UTC alignment

Enables reproducible demo with historical sample datasets.

---

# LLM Integration (Optional)

**LLM is NOT the source of truth for anomaly decisions.**

| Stage | LLM role |
|---|---|
| Anomaly detection | None — rule-based only |
| Incident summary | Optional enrichment |
| Alert creation | None — triggered by confirmed anomalies |

Providers: `template` (default, no API key), `gemini`, `openai`

Fields enriched: summary, what_happened, likely_cause, business_impact, recommended_action

---

# MetricWindow Aggregation

Fixed **10-minute buckets** scoped by app + service + endpoint:

| Metric | Source |
|---|---|
| error_count / error_rate | log.level = ERROR |
| http_5xx_count / http_5xx_rate | status 500–599 |
| latency_p95_ms | event.duration (nanoseconds → ms) |
| most_common_error_type | mode of error.type |

Overlapping uploads recompute buckets — no duplicate windows.

---

# Health Score Formula

```text
health_score = max(0, 100 - 25 × critical - 10 × warning)
```

- Counts anomalies in 24h before latest log timestamp
- No logs → neutral score of 100
- Cross-app isolation: anomalies scoped to selected app

---

# Demo Walkthrough

1. `make db && make migrate && make api`
2. `make dashboard` → http://localhost:8501
3. Create or select an app
4. **Load Sample Incident Dataset**
5. Wait for ingestion polling (`status: completed`)
6. Review:
   - Overview metrics and health score
   - Error / 5xx / latency trend charts
   - Detected anomalies table
   - Triggered alerts with webhook payloads
   - Incident summary panel
7. **Clear App Data** to reset

Sample data: `data/sample_incident_logs.jsonl` (1040+ events with incident spike)

---

# API-First Design

All flows exposed via REST — dashboard is a thin client:

- `POST /apps/{id}/logs/upload` — ingest JSONL
- `GET /apps/{id}/ingestion-runs/{run_id}` — poll status
- `GET /apps/{id}/dashboard/overview` — health metrics
- `GET /apps/{id}/dashboard/anomalies` — detected anomalies
- `GET /apps/{id}/alerts` — simulated alerts
- `GET /apps/{id}/incidents/summary` — enriched summaries

Interactive docs: http://localhost:8000/docs

---

# Validation And Testing

```bash
make test    # 92+ pytest tests, isolated watchdog_test DB
```

Coverage:

- ECS parser (dotted + nested fields, validation)
- Dedupe (event.id vs SHA-256, duplicate upload)
- Metric aggregation (buckets, grouping, rates)
- Anomaly detection (baselines, severity, stale cleanup)
- Health score (formula, relative time, cross-app isolation)
- End-to-end integration (upload → poll → anomalies → alerts → dashboard)

---

# No Paid Cloud Resources

| Resource | Status |
|---|---|
| Cloud database | Not used — local PostgreSQL |
| Cloud compute | Not used — local FastAPI + Streamlit |
| LLM API keys | Optional — template fallback works |
| Decommissioning | Not required — everything is local |

---

# AI Development Workflow

- Entire implementation generated through AI coding tool (Cursor)
- Full audit log maintained in `prompts.md`
- Conventional commits throughout development
- Service-repository pattern with pytest tests alongside features
- 6 development phases: foundation → ingestion → metrics → alerts → dashboard → testing → docs

---

# Final Submission Checklist

- [x] Public GitHub repository with complete source code
- [x] `prompts.md` — full AI audit log
- [x] `README.md` — setup, demo, and concept documentation
- [x] `architecture.md` — system design and trade-offs
- [x] `presentation.md` — this slide deck
- [x] Sample ECS JSONL logs in `data/`
- [x] Dashboard available locally
- [x] API docs available locally
- [ ] Tagle.ai result summary (separate submission)
- [x] No paid cloud resources used
- [x] No cloud decommissioning needed

---

# Thank You

**Observability Watchdog** — local, explainable, API-first SRE observability.

Repository: github.com/webboy/observability-watchdog

Questions welcome.
