"""Alert service tests."""

import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.alert import Alert
from app.models.anomaly import Anomaly
from app.models.anomaly_rule import AnomalyRule
from app.models.app import App
from app.services.alert_service import AlertService


def _create_app(db: Session) -> App:
    app = App(name="Platform", slug=f"platform-{uuid.uuid4().hex[:8]}", environment="production")
    db.add(app)
    db.commit()
    db.refresh(app)
    return app


def _create_anomaly(db: Session, app: App, *, severity: str = "CRITICAL") -> Anomaly:
    rule = db.scalar(select(AnomalyRule).where(AnomalyRule.metric_name == "error_count"))
    assert rule is not None
    window_start = datetime(2026, 6, 30, 11, 30, tzinfo=timezone.utc)
    anomaly = Anomaly(
        app_id=app.id,
        rule_id=rule.id,
        service_name="payment-service",
        url_path="/payments/charge",
        severity=severity,
        metric_name="error_count",
        window_start=window_start,
        window_end=window_start + timedelta(minutes=10),
        observed_value=47.0,
        baseline_value=3.2,
        anomaly_score=14.7,
        reason="error_count is 14.7x higher than baseline",
        likely_cause="UpstreamTimeout",
        recommended_action="Check payment provider status and inspect recent payment-service deployment",
    )
    db.add(anomaly)
    db.commit()
    db.refresh(anomaly)
    return anomaly


def test_alert_payload_shape_and_delivery_status(db_session: Session) -> None:
    """Simulated alerts should include the expected webhook payload fields."""
    app = _create_app(db_session)
    anomaly = _create_anomaly(db_session, app)

    alerts = AlertService(db_session).create_alerts_for_anomalies(app.id, [anomaly])
    db_session.commit()

    assert len(alerts) == 1
    payload = alerts[0].webhook_payload
    assert alerts[0].delivery_status == "simulated"
    assert payload["event_type"] == "anomaly.detected"
    assert payload["severity"] == "CRITICAL"
    assert payload["app_id"] == str(app.id)
    assert payload["anomaly_id"] == str(anomaly.id)
    assert payload["service_name"] == "payment-service"
    assert payload["url_path"] == "/payments/charge"
    assert payload["metric_name"] == "error_count"
    assert payload["observed_value"] == 47.0
    assert payload["baseline_value"] == 3.2
    assert payload["anomaly_score"] == 14.7
    assert payload["delivery_status"] == "simulated"
    assert "payment-service" in payload["message"]
    assert payload["reason"] == anomaly.reason
    assert payload["likely_cause"] == "UpstreamTimeout"
    assert payload["recommended_action"] == anomaly.recommended_action


def test_duplicate_alert_creation_is_idempotent(db_session: Session) -> None:
    """Re-running alert creation for the same anomaly should not duplicate rows."""
    app = _create_app(db_session)
    anomaly = _create_anomaly(db_session, app)
    service = AlertService(db_session)

    first = service.create_alerts_for_anomalies(app.id, [anomaly])
    second = service.create_alerts_for_anomalies(app.id, [anomaly])
    db_session.commit()

    assert len(first) == 1
    assert len(second) == 1
    assert first[0].id == second[0].id
    count = db_session.scalar(select(func.count()).select_from(Alert))
    assert count == 1
