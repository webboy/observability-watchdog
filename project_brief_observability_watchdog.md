# Project Brief: Intelligent Observability & Event Watchdog

## 1. Project Context

This project is a technical challenge for the **GenAI Engineer / Forward Deployed Engineer** hiring process.

The selected assignment is:

> Project 3: Intelligent Observability & Event Watchdog  
> Focus: Site Reliability (SRE). Develop a service that parses application or platform logs to detect anomalies or "spikes" in errors using AI logic. When thresholds are breached, the system must trigger a simulated webhook alert and visualize health trends.

The original assignment is intentionally open-ended. This project brief defines a concrete, realistic MVP scope that is still aligned with the assignment requirements.

The goal is not to build a full production observability platform. The goal is to demonstrate practical architecture, API-first implementation, AI-assisted anomaly detection, clear trade-offs, and a human-in-the-loop AI development workflow.

---

## 2. High-Level Product Idea

Build a local SRE observability service that monitors application health by ingesting structured log events, detecting abnormal spikes in errors or latency, creating simulated alerts, and visualizing health trends through a dashboard.

The system simulates a real-world scenario where an engineering or platform team wants to monitor multiple applications without setting up a full observability stack such as Elasticsearch, Datadog, Grafana, Prometheus, or OpenTelemetry Collector.

The MVP focuses on:

- application-level observability boundaries,
- ECS-compatible structured JSONL logs,
- API-first ingestion,
- anomaly detection through an isolated detection service,
- simulated webhook alerting,
- dashboard-based health visualization,
- explainable incident summaries.

---

## 3. Core Use Case

### Use Case: E-commerce Checkout / Payment Incident Detection

The demo scenario is an e-commerce platform composed of several services:

- `checkout-service`
- `payment-service`
- `inventory-service`
- `notification-service`
- `auth-service`

In normal operation, the `payment-service` has only a small number of errors per time window.

During an incident, the system receives a batch of ECS-compatible JSONL logs showing that:

- `payment-service` suddenly emits many `ERROR` log events,
- most errors happen on `/payments/charge`,
- HTTP 5xx responses increase sharply,
- p95 latency increases significantly,
- the dominant error type is `UpstreamTimeout` or `GatewayTimeout`.

The watchdog should detect this as an anomaly, classify the severity, generate a human-readable incident summary, create a simulated webhook alert, and show the impact in the dashboard.

Example incident interpretation:

```text
payment-service is experiencing a severe error spike on /payments/charge.
The current error count is significantly above the learned baseline.
Most failures are caused by upstream payment provider timeouts.
Likely business impact: failed checkouts and potential revenue loss.
Recommended action: check the payment provider status, inspect recent deployments, and enable retry/fallback logic if available.
```

---

## 4. Assignment Requirements Mapping

| Assignment Requirement | Project Decision |
|---|---|
| Python-based | Use Python with FastAPI |
| API-first | All ingestion, validation, detection, and alerting flows are exposed through REST APIs |
| Free database | Use PostgreSQL locally through Docker Compose; no paid cloud resources |
| Parse application/platform logs | Parse ECS-compatible JSONL/NDJSON logs |
| Detect anomalies/spikes in errors | Use an isolated anomaly detection service with baseline/spike scoring |
| Use AI logic | Use explainable AI-assisted anomaly scoring and incident intelligence; LLM may be optional for summaries |
| Trigger simulated webhook alert | Store generated alert payloads and mark them as simulated |
| Visualize health trends | Provide a dashboard for app health, error trends, anomalies, and alerts |
| Same AI tool end-to-end | Implementation must be generated through one AI coding tool only |
| No manual edits | All fixes and code changes must be requested from the AI tool |
| Audit log | Maintain `prompts.md` with all prompts used during implementation |
| Presentation deck | Include AI-generated `presentation.md` or PPT deck |
| Cloud resources decommissioned | No paid cloud resources are used; local Docker only |

---

## 5. Technical Positioning

This project should be positioned as a **local, API-first SRE watchdog MVP**.

It should not be presented as:

- a full Datadog replacement,
- a complete SIEM,
- a production log pipeline,
- an OpenTelemetry collector,
- a full admin platform,
- a multi-tenant SaaS product.

It should be presented as:

- a focused local observability MVP,
- a realistic technical slice of an SRE platform,
- a system designed for extensibility,
- a demonstration of AI-assisted engineering and architectural judgment.

---

## 6. Key Architectural Decisions

### 6.1 Use PostgreSQL Instead of SQLite

The assignment allows a free-tier database. PostgreSQL should be used locally via Docker Compose.

Reasons:

- more production-like than SQLite,
- better fit for log/event storage,
- supports `JSONB` for raw ECS event payloads,
- supports useful indexes,
- supports robust uniqueness constraints for deduplication,
- stronger signal for backend architecture maturity.

The project must not require any paid cloud database.

Recommended local setup:

```bash
docker compose up --build
```

### 6.2 Use ECS-Compatible JSONL Logs

The project should support **ECS-compatible JSONL/NDJSON application logs**.

Each line in the file is a single JSON object representing one log event.

This is a practical choice because:

- JSONL is easy to stream and parse line by line,
- ECS provides a known structured logging schema,
- ECS-style fields are readable and useful for SRE analysis,
- it avoids spending the challenge on arbitrary unstructured log parsing.

The system should not claim to parse every possible log format.

Explicitly supported:

- ECS-compatible JSONL / NDJSON files,
- one JSON object per line,
- API-submitted single event or batch event payloads.

Explicitly out of scope:

- arbitrary plain text logs,
- nginx/access log parsing,
- syslog parsing,
- Elasticsearch bulk export wrappers,
- Kibana saved search exports,
- vendor-specific log formats that require mapping adapters.

### 6.3 API-First with Dashboard as Client

The dashboard should not bypass backend logic.

Correct design:

```text
Dashboard → FastAPI endpoint → parser/validator → storage → anomaly detector → alert service
```

Incorrect design:

```text
Dashboard → direct database writes
```

The dashboard is only a convenience client for the API.

This preserves the API-first nature of the solution and allows reviewers to test the system with curl, Postman, Swagger UI, or the dashboard.

### 6.4 App as Observability Boundary

Introduce `App` as a lightweight monitored application entity.

An `App` represents the application or platform being observed.

Example:

```text
App: E-commerce Platform
Services inside the app:
- checkout-service
- payment-service
- inventory-service
```

Important distinction:

- `App` is a project/domain entity managed by this system.
- `service.name` comes from ECS log events.

Logs are ingested under an app context:

```http
POST /api/v1/apps/{app_id}/logs/upload
```

The ECS log event itself does not need to contain `app_id`.

### 6.5 Isolate Anomaly Detection

The anomaly detection logic must be isolated behind an `AnomalyDetectionService`.

The rest of the system should not depend on whether the detector is:

- rule-based,
- statistical,
- ML-based,
- LLM-assisted,
- replaced in the future.

The detector should operate on normalized metrics, not on raw uploaded files.

Correct flow:

```text
LogEvents
  ↓
MetricsAggregator
  ↓
AnomalyDetectionService
  ↓
Anomaly candidate
  ↓
Anomaly persistence
  ↓
AlertService
```


### 6.6 Execution Model: Background Post-Processing

The MVP uses a lightweight asynchronous post-processing model.

Log ingestion is split into two phases:

#### Request-Time Ingestion Phase

During the request, the API should:

- validate that the target `App` exists,
- create an `IngestionRun` record with status `processing`,
- parse the uploaded ECS-compatible JSONL file or submitted event batch,
- validate each event,
- normalize ECS dotted/nested fields,
- generate a dedupe key for each accepted event,
- insert only new `LogEvent` records into PostgreSQL,
- count accepted, rejected, and skipped duplicate events,
- return an API response with `ingestion_run_id` and ingestion counters.

#### Background Post-Processing Phase

After the initial ingestion response, the system should run background post-processing:

- identify affected time windows based on `LogEvent.timestamp`,
- aggregate metrics into fixed `MetricWindow` buckets,
- recompute affected metric windows from raw `LogEvent` records,
- run `AnomalyDetectionService`,
- create `Anomaly` records when abnormal patterns are detected,
- create simulated `Alert` records when anomaly severity breaches the alert threshold,
- generate incident summaries,
- update `IngestionRun` with detected anomaly and alert counts,
- mark `IngestionRun` as `completed` or `failed`.

For the MVP, background processing should use **FastAPI BackgroundTasks**.

Celery, Redis, RabbitMQ, and distributed workers are intentionally out of scope. They would be a natural production evolution if ingestion volume increased or if anomaly detection needed to scale independently.

The dashboard should treat ingestion as an asynchronous workflow:

```text
upload logs
  ↓
receive ingestion_run_id
  ↓
poll ingestion run status
  ↓
refresh health trends, anomalies, and alerts when completed
```

Recommended status endpoint:

```http
GET /api/v1/apps/{app_id}/ingestion-runs/{ingestion_run_id}
```

### 6.7 Time Semantics for Historical Bulk Uploads

Anomaly detection must be based on the timestamps inside the logs, not on the server execution time.

The system must not use `NOW()` as the basis for deciding which log windows are current during post-processing.

Reason:

A user may upload a historical JSONL file containing logs from three hours ago. The file may contain a normal period, an incident in the middle, and recovery afterwards. If detection only looks at server current time, the system will miss anomalies that happened inside the historical log timeline.

Correct approach:

```text
Use @timestamp from LogEvent records as the event timeline.
Detect anomalies relative to the fixed time windows inside that timeline.
```

During post-processing, the system should:

1. determine the minimum and maximum `LogEvent.timestamp` among newly inserted events,
2. identify affected fixed time buckets inside that timestamp range,
3. recompute metrics for those buckets from raw `LogEvent` records,
4. process affected buckets in chronological order,
5. calculate baseline relative to each bucket's `window_start`,
6. create anomalies for historical windows when their metrics deviate from the preceding baseline.

Example:

```text
Uploaded log range:
10:00–13:00

Fixed windows:
10:00–10:10
10:10–10:20
...
12:50–13:00

For window 11:30–11:40:
Baseline is calculated from windows before 11:30,
not from the server time when the upload happens.
```

This allows the system to detect incidents that occurred in historical or overlapping log uploads.

---

## 7. Core Entities

### 7.1 App

Represents a monitored application or platform.

Created manually through dashboard or API.

Fields:

```text
id
name
slug
description
environment
created_at
updated_at
```

Example:

```json
{
  "id": "app_01",
  "name": "E-commerce Platform",
  "slug": "ecommerce-platform",
  "description": "Demo checkout and payment platform",
  "environment": "production"
}
```

### 7.2 IngestionRun

Represents one ingestion attempt.

Created automatically when a user uploads a JSONL file or submits a batch of events.

Fields:

```text
id
app_id
source_type
source_name
filename
total_lines
accepted_events
rejected_events
skipped_duplicates
detected_anomalies
alerts_triggered
status
created_at
completed_at
```

Example response after upload:

```json
{
  "filename": "sample_logs.jsonl",
  "total_lines": 1200,
  "accepted_events": 1194,
  "skipped_duplicates": 0,
  "rejected_events": 6,
  "detected_anomalies": 2,
  "alerts_triggered": 1,
  "status": "completed"
}
```

### 7.3 LogEvent

Represents one valid parsed log event.

Created automatically from each valid ECS-compatible JSONL line or API-submitted event.

Fields:

```text
id
app_id
ingestion_run_id
event_id
dedupe_key
timestamp
service_name
log_level
message
event_dataset
event_outcome
event_duration_ns
http_status_code
url_path
trace_id
span_id
transaction_id
error_type
error_message
raw_event_json
created_at
```

Notes:

- `id` is internal UUID/ULID.
- `event_id` maps from ECS `event.id` if present.
- `dedupe_key` is used for idempotency and overlapping uploads.
- `raw_event_json` stores the original ECS-compatible JSON as `JSONB`.

### 7.4 AnomalyRule

Configuration entity used by the detector.

Rules are not the entire detection logic. They define guardrails such as metric selection, windows, minimum volume, and severity thresholds.

Fields:

```text
id
app_id nullable
name
metric_name
window_minutes
baseline_window_minutes
warning_multiplier
critical_multiplier
min_event_count
enabled
created_at
updated_at
```

If `app_id` is null, the rule is a global default.

For MVP, default rules can be seeded into the database and displayed read-only in the dashboard.

Recommended default rules:

1. Error count spike
2. HTTP 5xx rate spike
3. p95 latency spike

### 7.5 Anomaly

Represents a detected abnormal behavior.

Created automatically by the anomaly detection pipeline.

Fields:

```text
id
app_id
rule_id
service_name
url_path
severity
metric_name
window_start
window_end
observed_value
baseline_value
anomaly_score
reason
ai_summary
likely_cause
recommended_action
created_at
```

Example:

```json
{
  "app_id": "ecommerce-platform",
  "service_name": "payment-service",
  "url_path": "/payments/charge",
  "severity": "CRITICAL",
  "metric_name": "error_count",
  "observed_value": 47,
  "baseline_value": 3.2,
  "anomaly_score": 14.7,
  "reason": "Error count is 14.7x higher than baseline",
  "likely_cause": "External payment provider timeout",
  "recommended_action": "Check payment provider status and inspect recent payment-service deployment"
}
```

### 7.6 Alert

Represents a simulated webhook alert created from an anomaly.

Created automatically when an anomaly breaches the alert threshold.

Fields:

```text
id
app_id
anomaly_id
severity
delivery_status
webhook_payload
created_at
```

For MVP:

```text
delivery_status = simulated
```

Example payload:

```json
{
  "severity": "CRITICAL",
  "app": "E-commerce Platform",
  "service": "payment-service",
  "endpoint": "/payments/charge",
  "message": "Critical error spike detected in payment-service",
  "observed_value": 47,
  "baseline_value": 3.2,
  "recommended_action": "Check payment provider status and inspect recent deployment"
}
```


### 7.7 MetricWindow

Represents pre-aggregated metrics for one fixed time bucket.

Created or recomputed automatically during background post-processing after new `LogEvent` records are ingested.

Fields:

```text
id
app_id
service_name
url_path nullable
window_start
window_end
window_minutes
total_events
error_count
error_rate
http_5xx_count
http_5xx_rate
latency_p95_ms
unique_error_types
most_common_error_type
created_at
updated_at
```

Purpose:

- speeds up baseline calculations,
- avoids expensive repeated aggregation over raw logs,
- gives the dashboard ready-to-query health trend data,
- allows historical bulk uploads to be processed against their own event timeline.

Important:

`MetricWindow` values should be recomputed from raw `LogEvent` records for affected buckets. This avoids incorrect results when a later overlapping upload adds new events into an already existing historical time window.

Recommended uniqueness constraint:

```sql
CREATE UNIQUE INDEX uq_metric_windows_scope
ON metric_windows(app_id, service_name, COALESCE(url_path, ''), window_start, window_minutes);
```

Although this entity is listed after `Alert`, it is created before `Anomaly` in the processing pipeline:

```text
LogEvent → MetricWindow → Anomaly → Alert
```

---

## 8. Entity Lifecycle

### 8.1 App Lifecycle

Created manually:

```text
User creates App through dashboard or API.
```

API:

```http
POST /api/v1/apps
```

### 8.2 IngestionRun Lifecycle

Created automatically:

```text
User uploads file or submits events.
System creates IngestionRun.
System updates counters during ingestion.
System marks run as completed or failed.
```

### 8.3 LogEvent Lifecycle

Created automatically:

```text
Each valid ECS-compatible JSONL line becomes one LogEvent.
Invalid lines are rejected and counted in IngestionRun.
Duplicate events are skipped and counted as skipped_duplicates.
```


### 8.4 MetricWindow Lifecycle

Created or recomputed automatically during background post-processing.

```text
New LogEvents are inserted.
System identifies affected fixed time buckets based on LogEvent.timestamp.
For each affected bucket, system recomputes MetricWindow from raw LogEvent records.
MetricWindow records are then used by AnomalyDetectionService.
```

Metric windows are not created manually by users.

### 8.5 Anomaly Lifecycle

Created automatically:

```text
After ingestion, metrics are aggregated by app, service, endpoint, and time window.
The anomaly detector compares current behavior against baseline.
If abnormal behavior is detected, an Anomaly is created.
```

### 8.6 Alert Lifecycle

Created automatically:

```text
If Anomaly severity breaches alert threshold, AlertService creates a simulated webhook payload and stores it as an Alert.
```

---

## 9. Supported Log Format

### 9.1 JSONL / NDJSON Rules

The system accepts JSONL/NDJSON files where:

- file is UTF-8 text,
- each line is one valid JSON object,
- there is no outer JSON array,
- there are no commas between lines.

Example:

```jsonl
{"@timestamp":"2026-06-30T12:00:00Z","log.level":"INFO","message":"Checkout completed successfully","service.name":"checkout-service"}
{"@timestamp":"2026-06-30T12:01:00Z","log.level":"ERROR","message":"Payment provider timeout","service.name":"payment-service"}
```

### 9.2 Required Fields

For this MVP, the parser requires:

```text
@timestamp
log.level
message
service.name
```

### 9.3 Optional Fields

The parser should accept and use these fields when present:

```text
ecs.version
event.id
event.dataset
event.kind
event.category
event.type
event.outcome
event.duration
http.request.method
http.response.status_code
url.path
trace.id
span.id
transaction.id
error.type
error.message
```

### 9.4 ECS-Compatible Example

```json
{
  "@timestamp": "2026-06-30T12:01:00Z",
  "ecs.version": "9.4.0",
  "log.level": "ERROR",
  "message": "Payment provider timeout while charging customer",
  "service.name": "payment-service",
  "service.version": "2.1.0",
  "event.dataset": "payment.transaction",
  "event.kind": "event",
  "event.category": ["web"],
  "event.type": ["error"],
  "event.outcome": "failure",
  "event.duration": 4300000000,
  "http.request.method": "POST",
  "http.response.status_code": 502,
  "url.path": "/payments/charge",
  "trace.id": "0f9a2d7c8e1b4c6d0f9a2d7c8e1b4c6d",
  "error.type": "UpstreamTimeout",
  "error.message": "Payment provider timeout"
}
```

Important note:

`event.duration` follows ECS semantics and is stored in nanoseconds. The dashboard can convert it to milliseconds for display:

```text
duration_ms = event.duration / 1_000_000
```


### 9.5 ECS Dotted Keys and Nested JSON Support

The parser must support both common ECS JSON representations:

#### Flat dotted keys

```json
{
  "http.response.status_code": 502,
  "url.path": "/payments/charge",
  "service.name": "payment-service"
}
```

#### Nested objects

```json
{
  "http": {
    "response": {
      "status_code": 502
    }
  },
  "url": {
    "path": "/payments/charge"
  },
  "service": {
    "name": "payment-service"
  }
}
```

Both forms should be normalized into the same internal `LogEvent` fields before persistence:

```text
service.name                  → service_name
log.level                     → log_level
http.response.status_code     → http_status_code
url.path                      → url_path
event.duration                → event_duration_ns
trace.id                      → trace_id
error.type                    → error_type
error.message                 → error_message
```

If both dotted and nested versions of the same field are present, the parser should prefer the dotted key and add a validation warning.

The original event must still be stored unchanged in `raw_event_json`.

---

## 10. Event Identity and Deduplication

### 10.1 Problem

Uploaded log files may overlap.

Example:

1. User uploads a file with 100 events.
2. Later, user uploads another file with 200 events.
3. The second file contains the original 100 events plus 100 new events.

The system must avoid processing the first 100 events again.

### 10.2 Solution

Deduplicate per individual log event, not per file.

For each parsed event, generate a `dedupe_key`.

Priority:

```text
1. If ECS event.id exists:
   dedupe_key = app_id + event.id

2. If event.id is missing:
   dedupe_key = SHA-256 hash of selected normalized ECS fields
```

### 10.3 Why Not Timestamp + Service?

`@timestamp + service.name` is not enough.

A busy service can emit many events at the same timestamp or within the same second.

Using only timestamp and service would incorrectly collapse real events into duplicates.

### 10.4 Canonical Hash Fields

Recommended fields for fallback hash:

```text
app_id
@timestamp
service.name
log.level
message
event.dataset
event.outcome
event.duration
http.response.status_code
url.path
trace.id
span.id
transaction.id
error.type
error.message
```

The hash should be built from normalized JSON with stable key ordering.

### 10.5 Database Constraint

Recommended unique index:

```sql
CREATE UNIQUE INDEX uq_log_events_app_dedupe
ON log_events(app_id, dedupe_key);
```

### 10.6 Expected Behavior

First upload:

```json
{
  "total_lines": 100,
  "accepted_events": 100,
  "skipped_duplicates": 0,
  "rejected_events": 0
}
```

Second overlapping upload:

```json
{
  "total_lines": 200,
  "accepted_events": 100,
  "skipped_duplicates": 100,
  "rejected_events": 0
}
```

### 10.7 Production Note

When `event.id` is not present, canonical hashing is a best-effort idempotency strategy.

For production-grade ingestion, event producers should provide stable event IDs or source metadata such as file offset, collector ID, or stream offset.

---

## 11. API Design

### 11.1 App Endpoints

```http
POST   /api/v1/apps
GET    /api/v1/apps
GET    /api/v1/apps/{app_id}
DELETE /api/v1/apps/{app_id}
```

Optional update endpoint:

```http
PATCH /api/v1/apps/{app_id}
```

### 11.2 Log Ingestion Endpoints

Batch file upload:

```http
POST /api/v1/apps/{app_id}/logs/upload
Content-Type: multipart/form-data
```

Single or batch event ingestion:

```http
POST /api/v1/apps/{app_id}/logs/events
Content-Type: application/json
```

Validation-only endpoint:

```http
POST /api/v1/apps/{app_id}/logs/validate
```

### 11.3 Query Endpoints

```http
GET /api/v1/apps/{app_id}/logs/recent
GET /api/v1/apps/{app_id}/ingestion-runs
GET /api/v1/apps/{app_id}/ingestion-runs/{ingestion_run_id}
GET /api/v1/apps/{app_id}/health/trends
GET /api/v1/apps/{app_id}/anomalies
GET /api/v1/apps/{app_id}/alerts
GET /api/v1/apps/{app_id}/incidents/summary
```

### 11.4 Rule Endpoints

For MVP, rules can be read-only:

```http
GET /api/v1/apps/{app_id}/anomaly-rules
```

Optional later:

```http
PUT /api/v1/apps/{app_id}/anomaly-rules/{rule_id}
```

### 11.5 Demo Utility Endpoints

```http
POST /api/v1/apps/{app_id}/demo/load-sample-dataset
POST /api/v1/apps/{app_id}/demo/clear-data
```

These are useful for reviewers.


Clear data scope:

`POST /api/v1/apps/{app_id}/demo/clear-data` must not delete the `App` record itself.

It should delete only dynamic data associated with the selected app:

```text
log_events
metric_windows
ingestion_runs
anomalies
alerts
```

This allows the reviewer to reset the demo and perform a clean upload without recreating the app.


---

## 12. Dashboard Requirements

The dashboard should be an observability dashboard, not a full admin panel.

### 12.1 Required Dashboard Sections

#### 1. App Selector

Allows the user to select the monitored application.

If no app exists, user can create one.

#### 2. Data Ingestion

Includes:

- upload ECS-compatible JSONL file,
- load sample incident dataset,
- clear app data,
- show latest ingestion result.

Important: dashboard must call API endpoints, not write directly to DB.

#### 3. Overview Metrics

Display:

- total events ingested,
- accepted events,
- skipped duplicates,
- rejected events,
- active anomalies,
- alerts triggered,
- system health score.

#### 4. Health Trends

Display:

- errors over time,
- HTTP 5xx rate over time,
- p95 latency trend,
- service-level health trends.

#### 5. Top Failing Services

Display services ranked by:

- error count,
- error rate,
- 5xx count,
- latency.

#### 6. Anomalies

Display:

- service name,
- endpoint,
- severity,
- metric,
- observed value,
- baseline value,
- anomaly score,
- reason.

#### 7. Alerts

Display:

- latest simulated webhook payloads,
- severity,
- delivery status,
- timestamp.

#### 8. Incident Summary

Display AI-assisted incident explanation:

- what happened,
- affected service,
- likely cause,
- business impact,
- recommended action.

### 12.2 Dashboard Technology Options

Recommended:

```text
Streamlit dashboard + FastAPI backend
```

Alternative:

```text
Simple HTML/Jinja dashboard served by FastAPI
```

For fastest implementation, Streamlit is acceptable.


### 12.3 System Health Score

The dashboard must show a deterministic system health score.

For the MVP, calculate it from anomalies detected in the last 24 hours relative to the latest log timestamp for the app.

Use `latest_log_timestamp`, not server `NOW()`.

Formula:

```text
Health Score = max(
  0,
  100 - (25 × critical_anomalies) - (10 × warning_anomalies)
)
```

Scope:

```text
latest_log_timestamp = MAX(log_events.timestamp) for the selected app
score_window_start = latest_log_timestamp - 24 hours
```

Only anomalies with `window_end >= score_window_start` should affect the score.

Examples:

```text
0 critical, 0 warning → 100
1 critical, 0 warning → 75
1 critical, 2 warning  → 55
4 critical, 1 warning  → 0
```

This score is intentionally simple and explainable for the MVP. A production system could later weight severity, service criticality, incident duration, and recovery status.

---

## 13. Anomaly Detection Design

### 13.1 Design Principle

Do not use an LLM as the source of truth for anomaly decisions.

SRE anomaly detection should be:

- deterministic enough,
- explainable,
- repeatable,
- testable,
- auditable.

LLMs are better suited for summarization and interpretation, not final anomaly classification.

### 13.2 Hybrid AI-Assisted Detection

The anomaly engine should use a hybrid approach:

```text
Statistical / baseline-based detector → anomaly candidate
Rule guardrails → severity and alert threshold
GenAI / template intelligence → incident summary
```

### 13.3 Fixed Time Window Aggregation

Before detection, aggregate `LogEvent` records into fixed time windows.

The MVP should use fixed buckets, not sliding windows.

Default bucket size:

```text
10 minutes
```

Group by:

```text
app_id
service_name
url_path optional
window_start
window_end
```

Calculate and store in `MetricWindow`:

```text
total_events
error_count
error_rate
http_5xx_count
http_5xx_rate
latency_p95_ms
unique_error_types
most_common_error_type
```

Window boundaries are based on the event timestamps from `@timestamp`, not on server execution time.

Example:

```text
Event timestamp: 2026-06-30T12:04:38Z
Bucket: 2026-06-30T12:00:00Z → 2026-06-30T12:10:00Z
```

When a new upload inserts events into an already existing historical bucket, that bucket should be recomputed from raw `LogEvent` records and upserted into `MetricWindow`.

### 13.4 Baseline Comparison

For each analyzed fixed time window, compare the current `MetricWindow` against previous `MetricWindow` records.

The baseline is relative to the analyzed window, not to server time.

Default baseline:

```text
Previous 60 minutes = previous 6 windows of 10 minutes each
```

For a window `W`, the baseline query should look backwards from `W.window_start`:

```text
baseline_start = W.window_start - baseline_window_minutes
baseline_end   = W.window_start
```

The baseline should include metric windows for the same:

```text
app_id
service_name
url_path when available
metric_name
```

Example:

```text
Analyzed window:
11:30–11:40

Baseline window:
10:30–11:30

Server upload time:
14:20

Correct behavior:
Detection uses 10:30–11:30 as baseline, not 13:20–14:20 or NOW().
```

#### Baseline for `error_count`

Use the average of previous bucket values:

```text
baseline_error_count = AVG(metric_windows.error_count)
```

Example:

```text
Current 10-minute window:
payment-service has 47 errors.

Previous six 10-minute buckets:
2, 4, 3, 3, 5, 2 errors

Baseline:
3.16 errors

Spike ratio:
47 / 3.16 = 14.87x
```

#### Baseline for `http_5xx_rate`

Use the average of previous bucket-level 5xx rates:

```text
baseline_5xx_rate = AVG(metric_windows.http_5xx_rate)
```

This is fast and adequate for the MVP.

#### Baseline for `latency_p95_ms`

Use the average of previous bucket-level p95 latency values:

```text
baseline_latency_p95_ms = AVG(metric_windows.latency_p95_ms)
```

This is not statistically identical to calculating a global p95 over all raw events in the entire baseline period, but it is much faster and acceptable for the MVP.

Production note:

A production implementation could compute more accurate baselines using raw events, t-digest, histograms, Prometheus-style summaries, or a time-series database.

MVP decision:

```text
Baseline statistics are calculated from pre-aggregated MetricWindow values.
```

#### Division-by-Zero and Cold-Start Baselines

If the calculated baseline value is exactly 0 (e.g., during the initial ingestion phase where no historical data exists), the system should treat the baseline as `1.0` (or another configurable baseline floor) for spike ratio calculations to avoid division-by-zero errors.

### 13.5 Suggested Default Rules

#### Error Count Spike

```yaml
name: Error count spike
metric_name: error_count
window_minutes: 10
baseline_window_minutes: 60
warning_multiplier: 3
critical_multiplier: 8
min_event_count: 10
enabled: true
```

#### HTTP 5xx Rate Spike

```yaml
name: HTTP 5xx rate spike
metric_name: http_5xx_rate
window_minutes: 10
baseline_window_minutes: 60
warning_multiplier: 2
critical_multiplier: 5
min_event_count: 20
enabled: true
```

#### p95 Latency Spike

```yaml
name: Latency p95 spike
metric_name: latency_p95
window_minutes: 10
baseline_window_minutes: 60
warning_multiplier: 2
critical_multiplier: 4
min_event_count: 20
enabled: true
```


### 13.6 Rule Inheritance

`AnomalyRule` supports global defaults and app-specific overrides.

Rule resolution order:

```text
1. Look for an enabled rule with the same app_id and metric_name.
2. If found, use the app-specific rule.
3. If not found, use the enabled global default rule where app_id IS NULL.
4. If no rule exists, skip that metric.
```

This allows the system to start with sensible defaults while supporting per-application tuning.

Example:

```text
Global default:
error_count critical_multiplier = 8

E-commerce Platform override:
error_count critical_multiplier = 5

Result:
The detector uses 5 for E-commerce Platform and 8 for all other apps.
```

For the MVP, the dashboard may display rules read-only. Optional app-specific override editing can be added if time allows.

### 13.7 Extensibility

The detector should be designed so that future strategies can be added:

```text
AnomalyDetectionService
  └── DetectorStrategy
        ├── StatisticalBaselineDetector
        ├── RuleBasedDetector
        └── MLBasedDetector later
```

The MVP can use `StatisticalBaselineDetector` as default.

---

## 14. Incident Intelligence

After an anomaly is detected, the system should generate a human-readable incident summary.

This is the safest and most useful place for GenAI.

### 14.1 MVP-Safe Mode

Use deterministic template-based summaries from anomaly features.

Example:

```text
payment-service is experiencing a critical error spike on /payments/charge.
The current error count is 14.7x above baseline.
Most failures are HTTP 502 responses with error type UpstreamTimeout.
Likely impact: checkout failures and lost revenue risk.
Recommended action: check payment provider status and recent deployments.
```

### 14.2 Optional LLM Mode

The system should support a configurable LLM provider via environment variables:

- `LLM_PROVIDER` (e.g., `gemini` or `openai`, defaulting to `gemini` if a key is present).
- `GEMINI_API_KEY` or `OPENAI_API_KEY` to authenticate.

If a key is present, the system may generate richer incident summaries. If no key exists, fallback to deterministic summaries.

Important requirement:

```text
The project must run without any paid LLM API key.
```

### 14.3 Positioning

Recommended README wording:

```text
The system does not use an LLM as the source of truth for anomaly decisions. Detection is based on explainable baseline scoring and rule guardrails. GenAI is used in the incident intelligence layer to summarize detected anomalies, infer likely business impact, and suggest remediation steps.
```

---

## 15. Alerting Design

Alerts are simulated.

The system should not require Slack, PagerDuty, Teams, or any external webhook.

When an anomaly breaches the alert threshold:

```text
Anomaly → AlertService → simulated webhook payload → Alert stored in database
```

Example payload:

```json
{
  "event_type": "anomaly.detected",
  "severity": "CRITICAL",
  "app_id": "ecommerce-platform",
  "service_name": "payment-service",
  "url_path": "/payments/charge",
  "metric_name": "error_count",
  "observed_value": 47,
  "baseline_value": 3.2,
  "message": "Critical error spike detected in payment-service",
  "recommended_action": "Check payment provider status and recent deployments"
}
```

Store it with:

```text
delivery_status = simulated
```

---

## 16. Suggested Project Structure

```text
observability-watchdog/
  app/
    main.py
    config.py
    database.py
    models/
      app.py
      ingestion_run.py
      log_event.py
      metric_window.py
      anomaly_rule.py
      anomaly.py
      alert.py
    schemas/
      app.py
      log_ingestion.py
      anomaly.py
      alert.py
    api/
      apps.py
      logs.py
      health.py
      anomalies.py
      alerts.py
      demo.py
    services/
      ecs_parser.py
      log_ingestion_service.py
      metrics_aggregator.py
      anomaly_detection_service.py
      health_score_service.py
      incident_summary_service.py
      alert_service.py
      dedupe_service.py
    repositories/
      app_repository.py
      log_event_repository.py
      metric_window_repository.py
      anomaly_repository.py
      alert_repository.py
    seeds/
      anomaly_rules.py
  dashboard/
    streamlit_app.py
  data/
    sample_logs.jsonl
    sample_incident_logs.jsonl
  tests/
    test_ecs_parser.py
    test_dedupe_service.py
    test_anomaly_detection.py
    test_metric_aggregation.py
    test_health_score.py
    test_log_ingestion.py
  prompts.md
  README.md
  architecture.md
  presentation.md
  docker-compose.yml
  Dockerfile
  requirements.txt
  .env.example
```

---

## 17. Database Design Notes

### 17.1 PostgreSQL Features to Use

Use:

- `UUID` primary keys,
- `TIMESTAMPTZ` for timestamps,
- `JSONB` for `raw_event_json`,
- unique index on `(app_id, dedupe_key)`,
- indexes for trend queries.

### 17.2 Important Indexes

```sql
CREATE UNIQUE INDEX uq_log_events_app_dedupe
ON log_events(app_id, dedupe_key);

CREATE INDEX idx_log_events_app_timestamp
ON log_events(app_id, timestamp);

CREATE INDEX idx_log_events_app_service_timestamp
ON log_events(app_id, service_name, timestamp);

CREATE INDEX idx_log_events_app_level_timestamp
ON log_events(app_id, log_level, timestamp);

CREATE INDEX idx_log_events_raw_json
ON log_events USING GIN(raw_event_json);


CREATE UNIQUE INDEX uq_metric_windows_scope
ON metric_windows(app_id, service_name, COALESCE(url_path, ''), window_start, window_minutes);

CREATE INDEX idx_metric_windows_app_window
ON metric_windows(app_id, window_start);

CREATE INDEX idx_metric_windows_app_service_window
ON metric_windows(app_id, service_name, window_start);
```

---

## 18. Testing Strategy

Minimum tests:

### 18.1 ECS Parser Tests

Test:

- valid ECS-compatible event,
- missing required field,
- invalid timestamp,
- malformed JSONL line,
- optional fields handling,
- flat dotted ECS keys,
- nested ECS objects,
- dotted-vs-nested normalization.

### 18.2 Deduplication Tests

Test:

- same event uploaded twice,
- overlapping files,
- event with `event.id`,
- event without `event.id`,
- different events with same timestamp/service should not be deduped incorrectly.

### 18.3 Anomaly Detection Tests

Test:

- normal baseline no anomaly,
- error count spike creates anomaly,
- 5xx spike creates anomaly,
- latency spike creates anomaly,
- low event count does not create false alarm,
- historical bulk upload detects anomaly based on event timestamps,
- baseline uses previous MetricWindow buckets, not server current time,
- app-specific AnomalyRule overrides global defaults.

### 18.4 Metric Aggregation Tests

Test:

- fixed 10-minute buckets are calculated correctly,
- overlapping uploads recompute affected buckets,
- p95 latency is stored per bucket,
- baseline averages are calculated from previous bucket values.

### 18.5 Ingestion Tests

Test:

- file upload creates ingestion run,
- accepted/rejected/skipped counts are correct,
- anomalies created after ingestion,
- alerts created for critical anomalies.

---

## 19. Demo Flow for Reviewer

The reviewer should be able to run:

```bash
docker compose up --build
```

Then:

1. Open API docs.
2. Create an App or use pre-seeded demo app.
3. Upload `sample_incident_logs.jsonl`.
4. See ingestion summary.
5. Open dashboard.
6. Review health score.
7. Review error trends.
8. Review detected anomalies.
9. Review simulated alert payload.
10. Review incident summary.

Dashboard should also provide:

- `Load sample incident dataset`,
- `Clear app data`,
- `Upload JSONL file`.

---

## 20. Out of Scope

The following are intentionally out of scope for the MVP:

- real cloud resources,
- real webhook delivery,
- Slack/PagerDuty integration,
- Kafka or streaming ingestion,
- OpenTelemetry Collector,
- Kubernetes log tailing,
- arbitrary unstructured log parsing,
- user accounts and permissions,
- team/organization multi-tenancy,
- billing,
- production deployment,
- full ML training pipeline.

---

## 21. Risks and Trade-Offs

### 21.1 Log Format Risk

Risk:

The assignment only says "logs" and does not define a format.

Decision:

Use ECS-compatible JSONL as a clear input contract.

Rationale:

This is realistic, testable, and avoids wasting MVP time on arbitrary log parsing.

### 21.2 AI Logic Risk

Risk:

Using an LLM to decide anomalies would be unreliable.

Decision:

Use explainable baseline/spike scoring for anomaly detection and use GenAI only for incident summaries.

Rationale:

SRE decisions should be deterministic, auditable, and testable.

### 21.3 Scope Risk

Risk:

Adding too many admin features may distract from the challenge.

Decision:

Keep `App` CRUD minimal and focus on log ingestion, anomaly detection, alerts, and dashboard.

### 21.4 Database Setup Risk

Risk:

PostgreSQL adds setup complexity compared to SQLite.

Decision:

Use Docker Compose so the reviewer can run everything locally with one command.

---

## 22. Recommended README Summary

The README should include this positioning:

```text
This project is an API-first Intelligent Observability & Event Watchdog MVP. It ingests ECS-compatible JSONL application logs, stores normalized events in PostgreSQL, detects service-level error and latency anomalies using an explainable baseline scoring pipeline, creates simulated webhook alerts, and visualizes health trends through a dashboard.

The system supports multiple monitored applications. Each application acts as an observability boundary, while individual services are extracted from the ECS service.name field.

The anomaly detection logic is isolated behind an AnomalyDetectionService so the detection strategy can evolve without changing ingestion, storage, alerting, or dashboard code.

No paid cloud resources are used. The project runs locally with Docker Compose.
```

---

## 23. Required Initial AI Prompt

The assignment requires the following kind of initial prompt to the chosen AI coding tool.

Use this as the first prompt, adjusted for Project 3:

```text
Lead Architect mode: ON. We are building a Python-based, API-first Intelligent Observability & Event Watchdog using a free database and a dashboard.

Rules:
● No Manual Edits: You provide all logic and fixes. I will not edit any code.
● Audit Log: You must maintain a file named prompts.md. After every turn, update that file (or provide the text block) with the prompt I just used.
● Time-Check: Start a timer. Goal is an MVP in 4-6 hours (Max window: 16h). Report 'Elapsed Time' at the end of every response. Acknowledge and let's start.
```

Recommended second prompt:

```text
Before writing code, propose the complete architecture, API endpoints, database schema, dashboard screens, anomaly detection strategy, deduplication strategy, and final submission checklist. Keep the MVP realistic for a 48-hour hiring challenge.
```

---

## 24. Implementation Priorities

### Phase 1: Architecture and Skeleton

- FastAPI app
- PostgreSQL connection
- Docker Compose
- basic models
- health endpoint
- README skeleton
- prompts.md setup

### Phase 2: App and Ingestion

- App CRUD
- JSONL upload endpoint
- event ingestion endpoint
- ECS parser and validator
- ingestion runs
- dedupe logic

### Phase 3: Metrics and Detection

- metrics aggregation
- seeded anomaly rules
- anomaly detection service
- anomaly persistence

### Phase 4: Alerts and Incident Summary

- simulated alert payloads
- alert persistence
- deterministic incident summary
- optional LLM summary fallback design

### Phase 5: Dashboard

- app selector
- upload form
- load sample dataset
- overview metrics
- trends
- anomalies
- alerts
- incident summary

### Phase 6: Polish

- tests
- sample data
- README
- architecture.md
- presentation.md
- final submission checklist

---

## 25. Final Submission Checklist

- [ ] Public GitHub repository
- [ ] Complete source code
- [ ] `prompts.md` with full audit log
- [ ] README with setup and demo instructions
- [ ] Architecture document
- [ ] AI-generated presentation deck in Markdown or PPT
- [ ] Sample ECS-compatible JSONL logs
- [ ] Dashboard available locally
- [ ] API docs available locally
- [ ] Tagle.ai result summary included separately as required
- [ ] Confirmation that no paid cloud resources were used
- [ ] Confirmation that no cloud resources need decommissioning because the project runs locally

---

## 26. Final Positioning Statement

This project demonstrates a pragmatic Forward Deployed Engineering approach: taking an intentionally broad client brief, defining a realistic MVP scope, choosing sensible technical boundaries, building an API-first local system, isolating volatile AI/ML logic behind service boundaries, and delivering a demoable product with clear documentation and auditability.

The key architectural message is:

```text
The system keeps anomaly detection explainable and modular, uses GenAI where it is useful for incident understanding, and avoids unreliable black-box decisions in the critical alerting path.
```
