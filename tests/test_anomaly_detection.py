"""Anomaly detection tests."""

import uuid
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.anomaly import Anomaly
from app.models.anomaly_rule import AnomalyRule
from app.models.app import App
from app.models.metric_window import MetricWindow
from app.repositories.anomaly_rule_repository import AnomalyRuleRepository
from app.services.anomaly_detection_service import AnomalyDetectionService


def _create_app(db: Session) -> App:
    app = App(name="Test", slug=f"test-{uuid.uuid4().hex[:8]}", environment="production")
    db.add(app)
    db.commit()
    db.refresh(app)
    return app


def _add_window(
    db: Session,
    *,
    app_id: uuid.UUID,
    window_start: datetime,
    error_count: int = 0,
    http_5xx_rate: float = 0.0,
    latency_p95_ms: float | None = None,
    total_events: int = 30,
    service_name: str = "payment-service",
    url_path: str | None = "/payments/charge",
) -> MetricWindow:
    window = MetricWindow(
        app_id=app_id,
        service_name=service_name,
        url_path=url_path,
        window_start=window_start,
        window_end=window_start + timedelta(minutes=10),
        window_minutes=10,
        total_events=total_events,
        error_count=error_count,
        error_rate=error_count / total_events,
        http_5xx_count=int(http_5xx_rate * total_events),
        http_5xx_rate=http_5xx_rate,
        latency_p95_ms=latency_p95_ms,
    )
    db.add(window)
    db.commit()
    db.refresh(window)
    return window


def test_normal_baseline_creates_no_anomaly(db_session: Session) -> None:
    """Stable baseline windows should not create anomalies."""
    app = _create_app(db_session)
    base = datetime(2026, 6, 30, 10, 0, tzinfo=timezone.utc)
    for index in range(6):
        _add_window(db_session, app_id=app.id, window_start=base + timedelta(minutes=10 * index), error_count=2)

    current = _add_window(
        db_session,
        app_id=app.id,
        window_start=base + timedelta(minutes=60),
        error_count=3,
    )

    anomalies = AnomalyDetectionService(db_session).detect_for_windows([current])
    assert anomalies == []


def test_error_count_spike_creates_critical_anomaly(db_session: Session) -> None:
    """Large error spike should create a critical anomaly."""
    app = _create_app(db_session)
    base = datetime(2026, 6, 30, 10, 0, tzinfo=timezone.utc)
    for index in range(6):
        _add_window(db_session, app_id=app.id, window_start=base + timedelta(minutes=10 * index), error_count=2)

    current = _add_window(
        db_session,
        app_id=app.id,
        window_start=base + timedelta(minutes=60),
        error_count=47,
        total_events=50,
    )

    anomalies = AnomalyDetectionService(db_session).detect_for_windows([current])
    assert len(anomalies) == 1
    assert anomalies[0].severity == "CRITICAL"
    assert anomalies[0].metric_name == "error_count"


def test_min_event_count_suppresses_anomaly(db_session: Session) -> None:
    """Low-volume windows should not trigger anomalies."""
    app = _create_app(db_session)
    base = datetime(2026, 6, 30, 10, 0, tzinfo=timezone.utc)
    for index in range(6):
        _add_window(
            db_session,
            app_id=app.id,
            window_start=base + timedelta(minutes=10 * index),
            error_count=0,
            total_events=5,
        )

    current = _add_window(
        db_session,
        app_id=app.id,
        window_start=base + timedelta(minutes=60),
        error_count=5,
        total_events=5,
    )

    anomalies = AnomalyDetectionService(db_session).detect_for_windows([current])
    assert anomalies == []


def test_app_specific_rule_overrides_global_default(db_session: Session) -> None:
    """App-specific rules should override global defaults."""
    app = _create_app(db_session)
    db_session.add(
        AnomalyRule(
            app_id=app.id,
            name="App error count spike",
            metric_name="error_count",
            window_minutes=10,
            baseline_window_minutes=60,
            warning_multiplier=2,
            critical_multiplier=4,
            min_event_count=10,
            enabled=True,
        )
    )
    db_session.commit()

    base = datetime(2026, 6, 30, 10, 0, tzinfo=timezone.utc)
    for index in range(6):
        _add_window(db_session, app_id=app.id, window_start=base + timedelta(minutes=10 * index), error_count=2)

    current = _add_window(
        db_session,
        app_id=app.id,
        window_start=base + timedelta(minutes=60),
        error_count=10,
        total_events=20,
    )

    rule = AnomalyRuleRepository().resolve_rule(db_session, app.id, "error_count")
    assert rule is not None
    assert rule.app_id == app.id
    assert rule.critical_multiplier == 4

    anomalies = AnomalyDetectionService(db_session).detect_for_windows([current])
    assert len(anomalies) == 1
    assert anomalies[0].severity == "CRITICAL"


def test_baseline_lookup_uses_previous_sixty_minutes_only(db_session: Session) -> None:
    """Baseline lookup should ignore windows outside the previous 60 minutes."""
    app = _create_app(db_session)
    base = datetime(2026, 6, 30, 10, 0, tzinfo=timezone.utc)

    _add_window(db_session, app_id=app.id, window_start=base - timedelta(minutes=70), error_count=100)
    for index in range(6):
        _add_window(
            db_session,
            app_id=app.id,
            window_start=base + timedelta(minutes=10 * index),
            error_count=2,
        )
    _add_window(db_session, app_id=app.id, window_start=base + timedelta(minutes=70), error_count=100)

    current = _add_window(
        db_session,
        app_id=app.id,
        window_start=base + timedelta(minutes=60),
        error_count=47,
        total_events=50,
    )

    anomalies = AnomalyDetectionService(db_session).detect_for_windows([current])
    assert len(anomalies) == 1
    assert anomalies[0].baseline_value == 2.0


def test_cold_start_baseline_floors_to_one(db_session: Session) -> None:
    """Cold-start detection should floor baseline to 1.0 and compute score from observed value."""
    app = _create_app(db_session)
    current = _add_window(
        db_session,
        app_id=app.id,
        window_start=datetime(2026, 6, 30, 10, 0, tzinfo=timezone.utc),
        error_count=10,
        total_events=10,
    )

    anomalies = AnomalyDetectionService(db_session).detect_for_windows([current])
    assert len(anomalies) == 1
    assert anomalies[0].baseline_value == 1.0
    assert anomalies[0].anomaly_score == 10.0
    assert anomalies[0].severity == "CRITICAL"


def test_warning_severity_when_between_multipliers(db_session: Session) -> None:
    """Observed value between warning and critical multipliers should create WARNING."""
    app = _create_app(db_session)
    base = datetime(2026, 6, 30, 10, 0, tzinfo=timezone.utc)
    for index in range(6):
        _add_window(db_session, app_id=app.id, window_start=base + timedelta(minutes=10 * index), error_count=2)

    current = _add_window(
        db_session,
        app_id=app.id,
        window_start=base + timedelta(minutes=60),
        error_count=7,
        total_events=20,
    )

    anomalies = AnomalyDetectionService(db_session).detect_for_windows([current])
    assert len(anomalies) == 1
    assert anomalies[0].severity == "WARNING"
    assert anomalies[0].anomaly_score == pytest.approx(3.5)


def test_global_rule_used_when_no_app_specific_rule_exists(db_session: Session) -> None:
    """Apps without overrides should use the seeded global default rule."""
    app = _create_app(db_session)
    rule = AnomalyRuleRepository().resolve_rule(db_session, app.id, "error_count")

    assert rule is not None
    assert rule.app_id is None
    assert rule.warning_multiplier == 3.0
    assert rule.critical_multiplier == 8.0


def test_disabled_app_rule_falls_back_to_global_rule(db_session: Session) -> None:
    """Disabled app-specific rules should not override enabled global defaults."""
    app = _create_app(db_session)
    db_session.add(
        AnomalyRule(
            app_id=app.id,
            name="Disabled app rule",
            metric_name="error_count",
            window_minutes=10,
            baseline_window_minutes=60,
            warning_multiplier=1.1,
            critical_multiplier=1.2,
            min_event_count=1,
            enabled=False,
        )
    )
    db_session.commit()

    rule = AnomalyRuleRepository().resolve_rule(db_session, app.id, "error_count")
    assert rule is not None
    assert rule.app_id is None


def test_stale_anomaly_deleted_when_metric_returns_to_normal(db_session: Session) -> None:
    """Lowering metric values below threshold should remove stale anomalies."""
    app = _create_app(db_session)
    base = datetime(2026, 6, 30, 10, 0, tzinfo=timezone.utc)
    for index in range(6):
        _add_window(db_session, app_id=app.id, window_start=base + timedelta(minutes=10 * index), error_count=2)

    current = _add_window(
        db_session,
        app_id=app.id,
        window_start=base + timedelta(minutes=60),
        error_count=47,
        total_events=50,
    )
    AnomalyDetectionService(db_session).detect_for_windows([current])
    assert db_session.scalar(select(func.count()).select_from(Anomaly)) == 1

    current.error_count = 2
    current.error_rate = 2 / current.total_events
    db_session.commit()
    db_session.refresh(current)

    AnomalyDetectionService(db_session).detect_for_windows([current])
    db_session.flush()
    assert db_session.scalar(select(func.count()).select_from(Anomaly)) == 0
