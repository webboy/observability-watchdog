"""Data access helpers for MetricWindow entities."""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import and_, case, func, select
from sqlalchemy.orm import Session

from app.models.log_event import LogEvent
from app.models.metric_window import MetricWindow
from app.services.window_utils import WINDOW_MINUTES, window_end_from_start


class MetricWindowRepository:
    """Repository for metric window aggregation and retrieval."""

    @staticmethod
    def get_timestamp_range_for_run(
        db: Session,
        ingestion_run_id: uuid.UUID,
    ) -> tuple[datetime, datetime] | None:
        """Return min/max timestamps for events inserted in an ingestion run."""
        stmt = select(func.min(LogEvent.timestamp), func.max(LogEvent.timestamp)).where(
            LogEvent.ingestion_run_id == ingestion_run_id
        )
        result = db.execute(stmt).one()
        if result[0] is None or result[1] is None:
            return None
        return result[0], result[1]

    @staticmethod
    def aggregate_bucket(
        db: Session,
        *,
        app_id: uuid.UUID,
        window_start: datetime,
        window_minutes: int = WINDOW_MINUTES,
    ) -> list[dict[str, Any]]:
        """Aggregate raw log events for one bucket from all ingestion runs."""
        window_end = window_end_from_start(window_start, window_minutes)
        latency_ms = LogEvent.event_duration_ns / 1_000_000.0
        is_error = func.upper(LogEvent.log_level) == "ERROR"
        is_5xx = and_(LogEvent.http_status_code >= 500, LogEvent.http_status_code <= 599)

        base_filters = and_(
            LogEvent.app_id == app_id,
            LogEvent.timestamp >= window_start,
            LogEvent.timestamp < window_end,
        )

        grouped_stmt = (
            select(
                LogEvent.service_name,
                LogEvent.url_path,
                func.count().label("total_events"),
                func.sum(case((is_error, 1), else_=0)).label("error_count"),
                func.sum(case((is_5xx, 1), else_=0)).label("http_5xx_count"),
                func.count(func.distinct(LogEvent.error_type)).filter(LogEvent.error_type.is_not(None)).label(
                    "unique_error_types"
                ),
                func.percentile_cont(0.95)
                .within_group(latency_ms)
                .filter(LogEvent.event_duration_ns.is_not(None))
                .label("latency_p95_ms"),
            )
            .where(base_filters)
            .group_by(LogEvent.service_name, LogEvent.url_path)
        )

        rows = db.execute(grouped_stmt).all()
        aggregates: list[dict[str, Any]] = []

        for row in rows:
            total_events = int(row.total_events or 0)
            if total_events == 0:
                continue

            error_count = int(row.error_count or 0)
            http_5xx_count = int(row.http_5xx_count or 0)

            most_common_stmt = (
                select(LogEvent.error_type, func.count().label("cnt"))
                .where(
                    base_filters,
                    LogEvent.service_name == row.service_name,
                    LogEvent.url_path.is_not_distinct_from(row.url_path),
                    LogEvent.error_type.is_not(None),
                )
                .group_by(LogEvent.error_type)
                .order_by(func.count().desc())
                .limit(1)
            )
            most_common = db.execute(most_common_stmt).first()

            aggregates.append(
                {
                    "app_id": app_id,
                    "service_name": row.service_name,
                    "url_path": row.url_path,
                    "window_start": window_start,
                    "window_end": window_end,
                    "window_minutes": window_minutes,
                    "total_events": total_events,
                    "error_count": error_count,
                    "error_rate": error_count / total_events,
                    "http_5xx_count": http_5xx_count,
                    "http_5xx_rate": http_5xx_count / total_events,
                    "latency_p95_ms": float(row.latency_p95_ms) if row.latency_p95_ms is not None else None,
                    "unique_error_types": int(row.unique_error_types or 0),
                    "most_common_error_type": most_common.error_type if most_common else None,
                }
            )

        return aggregates

    @staticmethod
    def upsert_many(db: Session, rows: list[dict[str, Any]]) -> list[MetricWindow]:
        """Upsert metric window rows and return affected ORM objects."""
        if not rows:
            return []

        upserted: list[MetricWindow] = []
        for row in rows:
            existing = db.scalar(
                select(MetricWindow).where(
                    MetricWindow.app_id == row["app_id"],
                    MetricWindow.service_name == row["service_name"],
                    MetricWindow.window_start == row["window_start"],
                    MetricWindow.window_minutes == row["window_minutes"],
                    func.coalesce(MetricWindow.url_path, "") == (row.get("url_path") or ""),
                )
            )
            if existing:
                for key, value in row.items():
                    setattr(existing, key, value)
                upserted.append(existing)
            else:
                metric_window = MetricWindow(**row)
                db.add(metric_window)
                upserted.append(metric_window)

        db.flush()
        return upserted

    @staticmethod
    def list_for_bucket_starts(
        db: Session,
        *,
        app_id: uuid.UUID,
        window_starts: list[datetime],
        window_minutes: int = WINDOW_MINUTES,
    ) -> list[MetricWindow]:
        """Fetch metric windows for bucket starts in chronological order."""
        if not window_starts:
            return []

        stmt = (
            select(MetricWindow)
            .where(
                MetricWindow.app_id == app_id,
                MetricWindow.window_minutes == window_minutes,
                MetricWindow.window_start.in_(window_starts),
            )
            .order_by(MetricWindow.window_start.asc(), MetricWindow.service_name.asc(), MetricWindow.url_path.asc())
        )
        return list(db.scalars(stmt).all())

    @staticmethod
    def get_baseline_average(
        db: Session,
        *,
        app_id: uuid.UUID,
        service_name: str,
        url_path: str | None,
        window_start: datetime,
        window_minutes: int,
        baseline_window_minutes: int,
        metric_name: str,
    ) -> float | None:
        """Average metric value from the previous six windows before window_start."""
        metric_column_map = {
            "error_count": MetricWindow.error_count,
            "http_5xx_rate": MetricWindow.http_5xx_rate,
            "latency_p95": MetricWindow.latency_p95_ms,
        }
        metric_column = metric_column_map.get(metric_name)
        if metric_column is None:
            return None

        baseline_start = window_start - timedelta(minutes=baseline_window_minutes)
        previous_windows = (
            select(metric_column.label("metric_value"))
            .where(
                MetricWindow.app_id == app_id,
                MetricWindow.service_name == service_name,
                func.coalesce(MetricWindow.url_path, "") == (url_path or ""),
                MetricWindow.window_minutes == window_minutes,
                MetricWindow.window_start < window_start,
                MetricWindow.window_start >= baseline_start,
                metric_column.is_not(None),
            )
            .order_by(MetricWindow.window_start.desc())
            .limit(6)
            .subquery()
        )

        return db.scalar(select(func.avg(previous_windows.c.metric_value)))
