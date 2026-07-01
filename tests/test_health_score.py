"""Health score service tests."""

import uuid
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy.orm import Session

from app.models.anomaly import Anomaly
from app.models.anomaly_rule import AnomalyRule
from app.models.app import App
from app.models.ingestion_run import IngestionRun
from app.models.log_event import LogEvent
from app.services.health_score_service import HealthScoreService, calculate_health_score


@pytest.mark.parametrize(
    ("critical_count", "warning_count", "expected_score"),
    [
        (0, 0, 100),
        (1, 0, 75),
        (1, 2, 55),
        (4, 1, 0),
    ],
)
def test_calculate_health_score_formula(
    critical_count: int,
    warning_count: int,
    expected_score: int,
) -> None:
    """Health score formula should subtract 25 per critical and 10 per warning."""
    assert calculate_health_score(critical_count=critical_count, warning_count=warning_count) == expected_score


def _create_app(db: Session) -> App:
    app = App(name="Health", slug=f"health-{uuid.uuid4().hex[:8]}", environment="production")
    db.add(app)
    db.commit()
    db.refresh(app)
    return app


def _add_log(db: Session, app_id: uuid.UUID, timestamp: datetime) -> None:
    run = IngestionRun(app_id=app_id, source_type="test", source_name="health", status="completed")
    db.add(run)
    db.flush()
    db.add(
        LogEvent(
            app_id=app_id,
            ingestion_run_id=run.id,
            dedupe_key=f"dedupe-{uuid.uuid4()}",
            timestamp=timestamp,
            service_name="payment-service",
            log_level="INFO",
            message="ok",
            raw_event_json={"message": "ok"},
        )
    )
    db.commit()


def _add_anomaly(
    db: Session,
    *,
    app_id: uuid.UUID,
    severity: str,
    window_end: datetime,
) -> None:
    from sqlalchemy import select

    rule = db.scalar(
        select(AnomalyRule).where(
            AnomalyRule.metric_name == "error_count",
            AnomalyRule.app_id.is_(None),
        )
    )
    if rule is None:
        rule = AnomalyRule(
            app_id=None,
            name="Error count spike",
            metric_name="error_count",
            window_minutes=10,
            baseline_window_minutes=60,
            warning_multiplier=3.0,
            critical_multiplier=8.0,
            min_event_count=10,
            enabled=True,
        )
        db.add(rule)
        db.flush()

    db.add(
        Anomaly(
            app_id=app_id,
            rule_id=rule.id,
            service_name="payment-service",
            url_path="/payments/charge",
            severity=severity,
            metric_name="error_count",
            window_start=window_end - timedelta(minutes=10),
            window_end=window_end,
            observed_value=10.0,
            baseline_value=1.0,
            anomaly_score=10.0,
            reason="test anomaly",
        )
    )
    db.commit()


def test_only_recent_anomalies_count_toward_score(db_session: Session) -> None:
    """Only anomalies within 24h of latest log timestamp should affect score."""
    app = _create_app(db_session)
    latest = datetime(2026, 6, 30, 12, 0, tzinfo=timezone.utc)
    _add_log(db_session, app.id, latest)

    _add_anomaly(db_session, app_id=app.id, severity="CRITICAL", window_end=latest - timedelta(hours=25))
    _add_anomaly(db_session, app_id=app.id, severity="CRITICAL", window_end=latest - timedelta(hours=1))

    result = HealthScoreService(db_session).compute_for_app(app.id)

    assert result.system_health_score == 75
    assert result.critical_anomalies_24h == 1
    assert result.warning_anomalies_24h == 0


def test_health_score_uses_latest_log_timestamp_not_now(db_session: Session) -> None:
    """Health score window should anchor to MAX(log_events.timestamp), not server time."""
    app = _create_app(db_session)
    historical_latest = datetime(2026, 1, 1, 12, 0, tzinfo=timezone.utc)
    _add_log(db_session, app.id, historical_latest)
    _add_anomaly(
        db_session,
        app_id=app.id,
        severity="WARNING",
        window_end=historical_latest - timedelta(hours=2),
    )

    result = HealthScoreService(db_session).compute_for_app(app.id)

    assert result.latest_log_timestamp == historical_latest
    assert result.system_health_score == 90
    assert result.warning_anomalies_24h == 1


def test_anomalies_from_other_apps_do_not_affect_score(db_session: Session) -> None:
    """Anomalies belonging to another app should not change the selected app score."""
    app = _create_app(db_session)
    other_app = _create_app(db_session)
    latest = datetime(2026, 6, 30, 12, 0, tzinfo=timezone.utc)
    _add_log(db_session, app.id, latest)
    _add_anomaly(db_session, app_id=other_app.id, severity="CRITICAL", window_end=latest)

    result = HealthScoreService(db_session).compute_for_app(app.id)

    assert result.system_health_score == 100
    assert result.active_anomalies == 0


def test_no_logs_returns_neutral_score(db_session: Session) -> None:
    """Apps without logs should return a neutral score and no latest timestamp."""
    app = _create_app(db_session)

    result = HealthScoreService(db_session).compute_for_app(app.id)

    assert result.system_health_score == 100
    assert result.latest_log_timestamp is None
    assert result.active_anomalies == 0
