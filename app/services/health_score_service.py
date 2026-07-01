"""Deterministic system health score calculations."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.anomaly import Anomaly
from app.models.log_event import LogEvent


@dataclass(slots=True)
class HealthScoreResult:
    """Health score breakdown for one app."""

    system_health_score: int
    active_anomalies: int
    critical_anomalies_24h: int
    warning_anomalies_24h: int
    latest_log_timestamp: datetime | None


def calculate_health_score(*, critical_count: int, warning_count: int) -> int:
    """Apply the MVP health score formula."""
    return max(0, 100 - (25 * critical_count) - (10 * warning_count))


class HealthScoreService:
    """Compute health scores relative to latest log timestamps."""

    def __init__(self, db: Session) -> None:
        self.db = db

    def compute_for_app(self, app_id: uuid.UUID) -> HealthScoreResult:
        """Return health score using anomalies in the 24h window before latest log."""
        latest_log_timestamp = self.db.scalar(
            select(func.max(LogEvent.timestamp)).where(LogEvent.app_id == app_id)
        )
        if latest_log_timestamp is None:
            return HealthScoreResult(
                system_health_score=100,
                active_anomalies=0,
                critical_anomalies_24h=0,
                warning_anomalies_24h=0,
                latest_log_timestamp=None,
            )

        critical_count, warning_count = self._count_anomalies_in_window(
            app_id=app_id,
            latest_log_timestamp=latest_log_timestamp,
        )
        health_score = calculate_health_score(
            critical_count=critical_count,
            warning_count=warning_count,
        )
        return HealthScoreResult(
            system_health_score=health_score,
            active_anomalies=critical_count + warning_count,
            critical_anomalies_24h=critical_count,
            warning_anomalies_24h=warning_count,
            latest_log_timestamp=latest_log_timestamp,
        )

    def _count_anomalies_in_window(
        self,
        *,
        app_id: uuid.UUID,
        latest_log_timestamp: datetime,
    ) -> tuple[int, int]:
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

        critical_count = 0
        warning_count = 0
        for severity, count in severity_counts:
            if severity == "CRITICAL":
                critical_count = int(count)
            elif severity == "WARNING":
                warning_count = int(count)
        return critical_count, warning_count
