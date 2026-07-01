"""Dashboard and demo API tests."""

import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.models.anomaly import Anomaly
from app.models.anomaly_rule import AnomalyRule
from app.models.ingestion_run import IngestionRun
from app.models.log_event import LogEvent
from app.models.metric_window import MetricWindow


def _create_app(client: TestClient, slug: str | None = None) -> str:
    suffix = uuid.uuid4().hex[:8]
    response = client.post(
        "/api/v1/apps",
        json={
            "name": "Platform",
            "slug": slug or f"platform-{suffix}",
            "environment": "production",
        },
    )
    assert response.status_code == 201
    return response.json()["id"]


def _seed_metric_and_anomaly(db_session: Session, app_id: str) -> None:
    app_uuid = uuid.UUID(app_id)
    base = datetime(2026, 6, 30, 11, 0, tzinfo=timezone.utc)

    run = IngestionRun(app_id=app_uuid, source_type="test", source_name="seed", status="completed")
    db_session.add(run)
    db_session.flush()

    db_session.add(
        LogEvent(
            app_id=app_uuid,
            ingestion_run_id=run.id,
            dedupe_key=f"dedupe-{uuid.uuid4()}",
            timestamp=base + timedelta(minutes=30),
            service_name="payment-service",
            log_level="ERROR",
            message="fail",
            raw_event_json={"message": "fail"},
        )
    )

    for index in range(3):
        is_payment = index < 2
        db_session.add(
            MetricWindow(
                app_id=app_uuid,
                service_name="payment-service" if is_payment else "auth-service",
                url_path="/payments/charge" if is_payment else "/login",
                window_start=base + timedelta(minutes=10 * index),
                window_end=base + timedelta(minutes=10 * (index + 1)),
                window_minutes=10,
                total_events=100,
                error_count=40 if is_payment and index == 1 else 2,
                error_rate=0.4 if is_payment and index == 1 else 0.02,
                http_5xx_count=30 if is_payment and index == 1 else 1,
                http_5xx_rate=0.3 if is_payment and index == 1 else 0.01,
                latency_p95_ms=900.0 if is_payment and index == 1 else 120.0,
            )
        )

    rule = db_session.query(AnomalyRule).filter(AnomalyRule.metric_name == "error_count").one()
    db_session.add(
        Anomaly(
            app_id=app_uuid,
            rule_id=rule.id,
            service_name="payment-service",
            url_path="/payments/charge",
            severity="CRITICAL",
            metric_name="error_count",
            window_start=base + timedelta(minutes=20),
            window_end=base + timedelta(minutes=30),
            observed_value=40.0,
            baseline_value=2.0,
            anomaly_score=20.0,
            reason="error_count is 20.0x higher than baseline",
        )
    )
    db_session.commit()


def test_dashboard_overview_uses_latest_log_timestamp(client: TestClient, db_session: Session) -> None:
    """Health score should be computed relative to latest log timestamp."""
    app_id = _create_app(client)
    _seed_metric_and_anomaly(db_session, app_id)

    response = client.get(f"/api/v1/apps/{app_id}/dashboard/overview")
    assert response.status_code == 200
    payload = response.json()
    assert payload["total_logs"] == 1
    assert payload["active_anomalies"] == 1
    assert payload["system_health_score"] == 75
    assert payload["latest_log_timestamp"] is not None


def test_metric_windows_endpoint_returns_chart_rows(client: TestClient, db_session: Session) -> None:
    """Metric windows endpoint should return rows for health trend charts."""
    app_id = _create_app(client)
    _seed_metric_and_anomaly(db_session, app_id)

    response = client.get(f"/api/v1/apps/{app_id}/dashboard/metric-windows")
    assert response.status_code == 200
    items = response.json()["items"]
    assert len(items) == 3
    assert items[0]["service_name"] in {"payment-service", "auth-service"}


def test_top_failing_services_ranks_payment_service_first(client: TestClient, db_session: Session) -> None:
    """Top failing services should rank payment-service above auth-service."""
    app_id = _create_app(client)
    _seed_metric_and_anomaly(db_session, app_id)

    response = client.get(f"/api/v1/apps/{app_id}/dashboard/top-failing-services")
    assert response.status_code == 200
    items = response.json()["items"]
    assert len(items) >= 2
    assert items[0]["service_name"] == "payment-service"
    assert items[0]["rank"] == 1


def test_dashboard_anomalies_endpoint_returns_rows(client: TestClient, db_session: Session) -> None:
    """Dashboard anomalies endpoint should return latest anomaly rows."""
    app_id = _create_app(client)
    _seed_metric_and_anomaly(db_session, app_id)

    response = client.get(f"/api/v1/apps/{app_id}/dashboard/anomalies")
    assert response.status_code == 200
    items = response.json()["items"]
    assert len(items) == 1
    assert items[0]["severity"] == "CRITICAL"


def test_demo_clear_data_preserves_app(client: TestClient, db_session: Session) -> None:
    """Clear-data should remove dynamic rows but keep the app."""
    app_id = _create_app(client)
    _seed_metric_and_anomaly(db_session, app_id)

    response = client.post(f"/api/v1/apps/{app_id}/demo/clear-data")
    assert response.status_code == 200
    payload = response.json()
    assert payload["deleted_log_events"] == 1
    assert payload["deleted_metric_windows"] == 3
    assert payload["deleted_anomalies"] == 1

    app_response = client.get(f"/api/v1/apps/{app_id}")
    assert app_response.status_code == 200

    overview = client.get(f"/api/v1/apps/{app_id}/dashboard/overview").json()
    assert overview["total_logs"] == 0


def test_demo_load_sample_dataset_triggers_processing(client: TestClient, db_session: Session) -> None:
    """Sample dataset endpoint should ingest events and eventually create alerts."""
    if not Path("data/sample_incident_logs.jsonl").exists():
        return

    app_id = _create_app(client)
    response = client.post(f"/api/v1/apps/{app_id}/demo/load-sample-dataset")
    assert response.status_code == 201
    payload = response.json()
    assert payload["accepted_events"] > 0
    assert payload["status"] == "processing"

    status_response = client.get(
        f"/api/v1/apps/{app_id}/ingestion-runs/{payload['ingestion_run_id']}"
    )
    assert status_response.status_code == 200
    run_payload = status_response.json()
    assert run_payload["status"] == "completed"
    assert run_payload["alerts_triggered"] >= 1

    overview = client.get(f"/api/v1/apps/{app_id}/dashboard/overview").json()
    assert overview["total_logs"] > 0
    assert overview["triggered_alerts"] >= 1
