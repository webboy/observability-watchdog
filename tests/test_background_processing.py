"""Background processing integration tests."""

import io
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.alert import Alert
from app.models.app import App
from app.models.ingestion_run import IngestionRun
from app.models.log_event import LogEvent
from app.models.metric_window import MetricWindow
from app.services.background_processing_service import process_ingestion_run


def _create_app(client: TestClient) -> str:
    response = client.post(
        "/api/v1/apps",
        json={"name": "Platform", "slug": "platform-bg", "environment": "production"},
    )
    assert response.status_code == 201
    return response.json()["id"]


def test_ingestion_schedules_background_processing(client: TestClient, db_session: Session) -> None:
    """Ingestion with new events should eventually create metric windows."""
    app_id = _create_app(client)
    content = "\n".join(
        [
            '{"@timestamp":"2026-06-30T11:31:00Z","log.level":"ERROR","message":"fail","service.name":"payment-service","url.path":"/payments/charge","http.response.status_code":502,"error.type":"UpstreamTimeout","event.duration":4300000000}',
            '{"@timestamp":"2026-06-30T11:32:00Z","log.level":"ERROR","message":"fail","service.name":"payment-service","url.path":"/payments/charge","http.response.status_code":502,"error.type":"UpstreamTimeout","event.duration":4300000000}',
        ]
    )

    response = client.post(
        f"/api/v1/apps/{app_id}/logs/upload",
        files={"file": ("incident.jsonl", io.BytesIO(content.encode("utf-8")), "application/jsonl")},
    )

    assert response.status_code == 201
    payload = response.json()
    assert payload["accepted_events"] == 2

    status_response = client.get(
        f"/api/v1/apps/{app_id}/ingestion-runs/{payload['ingestion_run_id']}"
    )
    assert status_response.status_code == 200
    assert status_response.json()["status"] == "completed"

    metric_count = db_session.scalar(select(func.count()).select_from(MetricWindow))
    assert metric_count >= 1


def test_duplicate_only_ingestion_completes_without_background(db_session: Session, client: TestClient) -> None:
    """Duplicate-only ingestion should complete immediately."""
    app_id = _create_app(client)
    body = {
        "events": [
            {
                "@timestamp": "2026-06-30T12:01:00Z",
                "log.level": "ERROR",
                "message": "Payment timeout",
                "service.name": "payment-service",
            }
        ]
    }
    first = client.post(f"/api/v1/apps/{app_id}/logs/events", json=body)
    second = client.post(f"/api/v1/apps/{app_id}/logs/events", json=body)

    assert first.json()["status"] == "processing"
    assert second.json()["status"] == "completed"
    assert second.json()["skipped_duplicates"] == 1


def test_background_processing_marks_failed_on_exception(db_session: Session, monkeypatch) -> None:
    """Background failures should mark ingestion run failed."""
    app = App(name="Fail App", slug="fail-app", environment="production")
    db_session.add(app)
    db_session.commit()
    db_session.refresh(app)

    run = IngestionRun(app_id=app.id, source_type="test", source_name="test", status="processing")
    db_session.add(run)
    db_session.commit()
    db_session.refresh(run)

    db_session.add(
        LogEvent(
            app_id=app.id,
            ingestion_run_id=run.id,
            dedupe_key=f"dedupe-{uuid.uuid4()}",
            timestamp=datetime(2026, 6, 30, 12, 0, tzinfo=timezone.utc),
            service_name="payment-service",
            log_level="ERROR",
            message="fail",
            raw_event_json={"message": "fail"},
        )
    )
    db_session.commit()

    def boom(*args, **kwargs):
        raise RuntimeError("processing failed")

    monkeypatch.setattr(
        "app.services.background_processing_service.MetricsAggregator.recompute_for_ingestion_run",
        boom,
    )

    process_ingestion_run(run.id)
    db_session.refresh(run)
    assert run.status == "failed"


def test_background_processing_creates_alerts_and_updates_run(db_session: Session) -> None:
    """Detected anomalies should produce simulated alerts and update alerts_triggered."""
    app = App(name="Incident App", slug=f"incident-{uuid.uuid4().hex[:8]}", environment="production")
    db_session.add(app)
    db_session.commit()
    db_session.refresh(app)

    run = IngestionRun(app_id=app.id, source_type="upload", source_name="incident.jsonl", status="processing")
    db_session.add(run)
    db_session.commit()
    db_session.refresh(run)

    base = datetime(2026, 6, 30, 10, 0, tzinfo=timezone.utc)
    dedupe_index = 0

    def add_event(ts: datetime, *, error: bool) -> None:
        nonlocal dedupe_index
        dedupe_index += 1
        db_session.add(
            LogEvent(
                app_id=app.id,
                ingestion_run_id=run.id,
                dedupe_key=f"dedupe-{dedupe_index}",
                timestamp=ts,
                service_name="payment-service",
                url_path="/payments/charge",
                log_level="ERROR" if error else "INFO",
                message="Payment timeout" if error else "ok",
                http_status_code=502 if error else 200,
                raw_event_json={"message": "event"},
            )
        )

    for bucket_index in range(6):
        bucket_start = base + timedelta(minutes=10 * bucket_index)
        for event_index in range(30):
            add_event(bucket_start + timedelta(seconds=event_index), error=event_index < 2)

    spike_start = base + timedelta(minutes=60)
    for event_index in range(50):
        add_event(spike_start + timedelta(seconds=event_index), error=event_index < 47)

    db_session.commit()

    process_ingestion_run(run.id)
    db_session.expire_all()

    refreshed_run = db_session.get(IngestionRun, run.id)
    assert refreshed_run is not None
    assert refreshed_run.status == "completed"
    assert refreshed_run.detected_anomalies >= 1
    assert refreshed_run.alerts_triggered >= 1

    alert_count = db_session.scalar(select(func.count()).select_from(Alert))
    assert alert_count >= 1


def test_background_processing_with_sample_incident_file(client: TestClient, db_session: Session) -> None:
    """Uploading the sample incident dataset should eventually create alerts."""
    sample_path = Path("data/sample_incident_logs.jsonl")
    if not sample_path.exists():
        return

    app_id = _create_app(client)
    with sample_path.open("rb") as handle:
        response = client.post(
            f"/api/v1/apps/{app_id}/logs/upload",
            files={"file": ("sample_incident_logs.jsonl", handle, "application/jsonl")},
        )

    assert response.status_code == 201
    payload = response.json()
    assert payload["accepted_events"] > 0

    status_response = client.get(
        f"/api/v1/apps/{app_id}/ingestion-runs/{payload['ingestion_run_id']}"
    )
    assert status_response.status_code == 200
    run_payload = status_response.json()
    assert run_payload["status"] == "completed"
    assert run_payload["alerts_triggered"] >= 1

    alerts_response = client.get(f"/api/v1/apps/{app_id}/alerts")
    assert alerts_response.status_code == 200
    assert len(alerts_response.json()["items"]) >= 1
