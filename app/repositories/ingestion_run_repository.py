"""Data access helpers for IngestionRun entities."""

import uuid
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.models.ingestion_run import IngestionRun


class IngestionRunRepository:
    """Repository for ingestion run lifecycle operations."""

    @staticmethod
    def create(
        db: Session,
        *,
        app_id: uuid.UUID,
        source_type: str,
        source_name: str | None = None,
        filename: str | None = None,
    ) -> IngestionRun:
        """Create a new ingestion run in processing status."""
        run = IngestionRun(
            app_id=app_id,
            source_type=source_type,
            source_name=source_name,
            filename=filename,
            status="processing",
        )
        db.add(run)
        db.flush()
        return run

    @staticmethod
    def finalize(
        db: Session,
        run: IngestionRun,
        *,
        total_lines: int,
        accepted_events: int,
        rejected_events: int,
        skipped_duplicates: int,
        status: str = "completed",
    ) -> IngestionRun:
        """Update counters and mark the ingestion run complete."""
        run.total_lines = total_lines
        run.accepted_events = accepted_events
        run.rejected_events = rejected_events
        run.skipped_duplicates = skipped_duplicates
        run.status = status
        run.completed_at = datetime.now(timezone.utc)
        db.add(run)
        db.commit()
        db.refresh(run)
        return run

    @staticmethod
    def mark_failed(db: Session, run: IngestionRun) -> IngestionRun:
        """Mark an ingestion run as failed."""
        run.status = "failed"
        run.completed_at = datetime.now(timezone.utc)
        db.add(run)
        db.commit()
        db.refresh(run)
        return run
