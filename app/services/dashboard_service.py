"""Dashboard aggregation and health score calculations."""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.alert import Alert
from app.models.anomaly import Anomaly
from app.models.ingestion_run import IngestionRun
from app.models.log_event import LogEvent
from app.models.metric_window import MetricWindow
from app.repositories.anomaly_repository import AnomalyRepository
from app.repositories.metric_window_repository import MetricWindowRepository
from app.schemas.dashboard import (
    DashboardOverviewRead,
    TopFailingServiceRead,
)


class DashboardService:
    """Compute dashboard overview metrics and service rankings."""

    def __init__(self, db: Session) -> None:
        self.db = db
        self.metric_repo = MetricWindowRepository()
        self.anomaly_repo = AnomalyRepository()

    def get_overview(self, app_id: uuid.UUID) -> DashboardOverviewRead:
        """Return overview metrics and deterministic health score."""
        total_logs = self.db.scalar(
            select(func.count()).select_from(LogEvent).where(LogEvent.app_id == app_id)
        ) or 0

        ingestion_totals = self.db.execute(
            select(
                func.coalesce(func.sum(IngestionRun.accepted_events), 0),
                func.coalesce(func.sum(IngestionRun.rejected_events), 0),
                func.coalesce(func.sum(IngestionRun.skipped_duplicates), 0),
            ).where(IngestionRun.app_id == app_id)
        ).one()

        triggered_alerts = self.db.scalar(
            select(func.count()).select_from(Alert).where(Alert.app_id == app_id)
        ) or 0

        latest_log_timestamp = self.db.scalar(
            select(func.max(LogEvent.timestamp)).where(LogEvent.app_id == app_id)
        )

        critical_count = 0
        warning_count = 0
        if latest_log_timestamp is not None:
            score_window_start = latest_log_timestamp - timedelta(hours=24)
            severity_counts = self.db.execute(
                select(Anomaly.severity, func.count())
                .where(
                    Anomaly.app_id == app_id,
                    Anomaly.window_end >= score_window_start,
                    Anomaly.severity.in_(["CRITICAL", "WARNING"]),
                )
                .group_by(Anomaly.severity)
            ).all()
            for severity, count in severity_counts:
                if severity == "CRITICAL":
                    critical_count = int(count)
                elif severity == "WARNING":
                    warning_count = int(count)

        active_anomalies = critical_count + warning_count
        health_score = max(0, 100 - (25 * critical_count) - (10 * warning_count))

        return DashboardOverviewRead(
            total_logs=int(total_logs),
            accepted_events=int(ingestion_totals[0]),
            rejected_events=int(ingestion_totals[1]),
            skipped_duplicates=int(ingestion_totals[2]),
            active_anomalies=active_anomalies,
            triggered_alerts=int(triggered_alerts),
            system_health_score=health_score,
            latest_log_timestamp=latest_log_timestamp,
            critical_anomalies_24h=critical_count,
            warning_anomalies_24h=warning_count,
        )

    def get_top_failing_services(self, app_id: uuid.UUID, *, limit: int = 10) -> list[TopFailingServiceRead]:
        """Rank services by weighted failure score from metric windows."""
        rows = self.db.execute(
            select(
                MetricWindow.service_name,
                func.sum(MetricWindow.total_events).label("total_events"),
                func.sum(MetricWindow.error_count).label("error_count"),
                func.sum(MetricWindow.http_5xx_count).label("http_5xx_count"),
                func.avg(MetricWindow.error_rate).label("avg_error_rate"),
                func.max(MetricWindow.latency_p95_ms).label("max_p95_latency_ms"),
            )
            .where(MetricWindow.app_id == app_id)
            .group_by(MetricWindow.service_name)
        ).all()

        ranked: list[TopFailingServiceRead] = []
        for row in rows:
            error_count = int(row.error_count or 0)
            http_5xx_count = int(row.http_5xx_count or 0)
            avg_error_rate = float(row.avg_error_rate or 0.0)
            max_p95 = float(row.max_p95_latency_ms) if row.max_p95_latency_ms is not None else None
            latency_component = (max_p95 or 0.0) / 1000.0
            failure_score = (
                error_count * 1.0
                + http_5xx_count * 1.5
                + avg_error_rate * 100.0
                + latency_component
            )
            ranked.append(
                TopFailingServiceRead(
                    rank=0,
                    service_name=row.service_name,
                    total_events=int(row.total_events or 0),
                    error_count=error_count,
                    http_5xx_count=http_5xx_count,
                    avg_error_rate=avg_error_rate,
                    max_p95_latency_ms=max_p95,
                    failure_score=round(failure_score, 2),
                )
            )

        ranked.sort(key=lambda item: item.failure_score, reverse=True)
        for index, item in enumerate(ranked[:limit], start=1):
            item.rank = index
        return ranked[:limit]

    @staticmethod
    def list_metric_windows(db: Session, app_id: uuid.UUID, *, limit: int = 500) -> list[MetricWindow]:
        """Return metric windows for charting ordered by window start."""
        stmt = (
            select(MetricWindow)
            .where(MetricWindow.app_id == app_id)
            .order_by(MetricWindow.window_start.asc(), MetricWindow.service_name.asc(), MetricWindow.url_path.asc())
            .limit(limit)
        )
        return list(db.scalars(stmt).all())
