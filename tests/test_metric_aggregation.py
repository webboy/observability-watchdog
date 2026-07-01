"""Metric aggregation tests."""

import uuid
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.models.app import App
from app.models.ingestion_run import IngestionRun
from app.models.log_event import LogEvent
from app.services.metrics_aggregator import MetricsAggregator
from app.services.window_utils import floor_to_window_start


def _create_app(db: Session) -> App:
    app = App(name="Test", slug=f"test-{uuid.uuid4().hex[:8]}", environment="production")
    db.add(app)
    db.commit()
    db.refresh(app)
    return app


def _create_run(db: Session, app_id: uuid.UUID) -> IngestionRun:
    run = IngestionRun(app_id=app_id, source_type="test", source_name="test")
    db.add(run)
    db.commit()
    db.refresh(run)
    return run


def _add_event(
    db: Session,
    *,
    app_id: uuid.UUID,
    run_id: uuid.UUID,
    timestamp: datetime,
    service_name: str = "payment-service",
    log_level: str = "INFO",
    url_path: str | None = "/payments/charge",
    http_status_code: int = 200,
    event_duration_ns: int | None = 100_000_000,
    error_type: str | None = None,
) -> None:
    db.add(
        LogEvent(
            app_id=app_id,
            ingestion_run_id=run_id,
            dedupe_key=f"dedupe-{uuid.uuid4()}",
            timestamp=timestamp,
            service_name=service_name,
            log_level=log_level,
            message="test event",
            url_path=url_path,
            http_status_code=http_status_code,
            event_duration_ns=event_duration_ns,
            error_type=error_type,
            raw_event_json={"message": "test event"},
        )
    )


def test_events_bucketed_into_fixed_ten_minute_windows(db_session: Session) -> None:
    """Events should aggregate into fixed 10-minute buckets."""
    app = _create_app(db_session)
    run = _create_run(db_session, app.id)
    bucket_start = datetime(2026, 6, 30, 11, 30, tzinfo=timezone.utc)

    _add_event(db_session, app_id=app.id, run_id=run.id, timestamp=bucket_start.replace(minute=31))
    _add_event(db_session, app_id=app.id, run_id=run.id, timestamp=bucket_start.replace(minute=35))
    db_session.commit()

    windows = MetricsAggregator(db_session).recompute_for_ingestion_run(run.id, app.id)

    assert len(windows) == 1
    assert windows[0].window_start == bucket_start
    assert windows[0].total_events == 2


def test_overlapping_upload_recomputes_existing_bucket(db_session: Session) -> None:
    """Later uploads should recompute affected buckets from all raw events."""
    app = _create_app(db_session)
    run_one = _create_run(db_session, app.id)
    run_two = _create_run(db_session, app.id)
    bucket_start = datetime(2026, 6, 30, 11, 30, tzinfo=timezone.utc)

    _add_event(db_session, app_id=app.id, run_id=run_one.id, timestamp=bucket_start.replace(minute=31))
    db_session.commit()
    MetricsAggregator(db_session).recompute_for_ingestion_run(run_one.id, app.id)

    _add_event(
        db_session,
        app_id=app.id,
        run_id=run_two.id,
        timestamp=bucket_start.replace(minute=33),
        log_level="ERROR",
        http_status_code=502,
        error_type="UpstreamTimeout",
    )
    db_session.commit()

    windows = MetricsAggregator(db_session).recompute_for_ingestion_run(run_two.id, app.id)

    assert len(windows) == 1
    assert windows[0].total_events == 2
    assert windows[0].error_count == 1


def test_p95_latency_stored_in_milliseconds(db_session: Session) -> None:
    """Latency p95 should be computed from event duration nanoseconds."""
    app = _create_app(db_session)
    run = _create_run(db_session, app.id)
    bucket_start = floor_to_window_start(datetime(2026, 6, 30, 12, 0, tzinfo=timezone.utc))

    for duration_ns in [100_000_000, 200_000_000, 300_000_000, 400_000_000, 500_000_000]:
        _add_event(
            db_session,
            app_id=app.id,
            run_id=run.id,
            timestamp=bucket_start.replace(minute=1),
            event_duration_ns=duration_ns,
        )
    db_session.commit()

    windows = MetricsAggregator(db_session).recompute_for_ingestion_run(run.id, app.id)

    assert windows[0].latency_p95_ms >= 400.0
