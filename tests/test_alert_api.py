"""Alert and incident API tests."""

import uuid
from datetime import datetime, timedelta, timezone

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.models.anomaly import Anomaly
from app.models.anomaly_rule import AnomalyRule
from app.models.app import App
from app.services.alert_service import AlertService
from app.services.incident_summary_service import IncidentSummaryService


def _create_app(client: TestClient) -> str:
    response = client.post(
        "/api/v1/apps",
        json={"name": "Platform", "slug": f"platform-{uuid.uuid4().hex[:8]}", "environment": "production"},
    )
    assert response.status_code == 201
    return response.json()["id"]


def _seed_anomaly_with_alert(db_session: Session, app_id: str) -> None:
    rule = db_session.query(AnomalyRule).filter(AnomalyRule.metric_name == "error_count").one()
    window_start = datetime(2026, 6, 30, 11, 30, tzinfo=timezone.utc)
    anomaly = Anomaly(
        app_id=uuid.UUID(app_id),
        rule_id=rule.id,
        service_name="payment-service",
        url_path="/payments/charge",
        severity="CRITICAL",
        metric_name="error_count",
        window_start=window_start,
        window_end=window_start + timedelta(minutes=10),
        observed_value=47.0,
        baseline_value=3.2,
        anomaly_score=14.7,
        reason="error_count is 14.7x higher than baseline",
    )
    db_session.add(anomaly)
    db_session.commit()
    db_session.refresh(anomaly)

    enriched = IncidentSummaryService(db_session).enrich_anomalies([anomaly])
    AlertService(db_session).create_alerts_for_anomalies(uuid.UUID(app_id), enriched)
    db_session.commit()


def test_list_alerts_for_app(client: TestClient, db_session: Session) -> None:
    """Alert listing endpoint should return simulated alerts for an app."""
    app_id = _create_app(client)
    _seed_anomaly_with_alert(db_session, app_id)

    response = client.get(f"/api/v1/apps/{app_id}/alerts")
    assert response.status_code == 200
    payload = response.json()
    assert len(payload["items"]) == 1
    assert payload["items"][0]["severity"] == "CRITICAL"
    assert payload["items"][0]["delivery_status"] == "simulated"
    assert payload["items"][0]["webhook_payload"]["service_name"] == "payment-service"


def test_list_alerts_filter_by_service_name(client: TestClient, db_session: Session) -> None:
    """Alert listing should support service_name filtering."""
    app_id = _create_app(client)
    _seed_anomaly_with_alert(db_session, app_id)

    response = client.get(
        f"/api/v1/apps/{app_id}/alerts",
        params={"service_name": "payment-service"},
    )
    assert response.status_code == 200
    assert len(response.json()["items"]) == 1

    empty = client.get(
        f"/api/v1/apps/{app_id}/alerts",
        params={"service_name": "auth-service"},
    )
    assert empty.status_code == 200
    assert empty.json()["items"] == []


def test_incident_summary_endpoint_returns_latest_summary(client: TestClient, db_session: Session) -> None:
    """Incident summary endpoint should return enriched anomaly summaries."""
    app_id = _create_app(client)
    _seed_anomaly_with_alert(db_session, app_id)

    response = client.get(f"/api/v1/apps/{app_id}/incidents/summary")
    assert response.status_code == 200
    payload = response.json()
    assert len(payload["items"]) == 1
    assert payload["items"][0]["service_name"] == "payment-service"
    assert payload["items"][0]["summary"]
    assert payload["items"][0]["likely_cause"]
    assert payload["items"][0]["recommended_action"]


def test_alerts_endpoint_returns_404_for_missing_app(client: TestClient) -> None:
    """Unknown app IDs should return 404 on alert endpoints."""
    missing = uuid.uuid4()
    response = client.get(f"/api/v1/apps/{missing}/alerts")
    assert response.status_code == 404
