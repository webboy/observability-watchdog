"""Metric aggregation service for fixed time windows."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy.orm import Session

from app.models.metric_window import MetricWindow
from app.repositories.metric_window_repository import MetricWindowRepository
from app.services.window_utils import WINDOW_MINUTES, floor_to_window_start, iter_window_starts


class MetricsAggregator:
    """Recompute affected metric windows from raw log events."""

    def __init__(self, db: Session) -> None:
        self.db = db
        self.metric_repo = MetricWindowRepository()

    def recompute_for_ingestion_run(self, ingestion_run_id: uuid.UUID, app_id: uuid.UUID) -> list[MetricWindow]:
        """Recompute all metric windows affected by newly inserted events."""
        timestamp_range = self.metric_repo.get_timestamp_range_for_run(self.db, ingestion_run_id)
        if timestamp_range is None:
            return []

        min_timestamp, max_timestamp = timestamp_range
        bucket_starts = iter_window_starts(min_timestamp, max_timestamp, WINDOW_MINUTES)
        return self.recompute_buckets(app_id=app_id, bucket_starts=bucket_starts)

    def recompute_buckets(self, *, app_id: uuid.UUID, bucket_starts: list[datetime]) -> list[MetricWindow]:
        """Recompute metric windows for explicit bucket starts."""
        all_rows: list[dict] = []
        for bucket_start in bucket_starts:
            all_rows.extend(
                self.metric_repo.aggregate_bucket(
                    self.db,
                    app_id=app_id,
                    window_start=bucket_start,
                    window_minutes=WINDOW_MINUTES,
                )
            )

        return self.metric_repo.upsert_many(self.db, all_rows)
