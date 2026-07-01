"""Data access helpers for LogEvent bulk inserts."""

from typing import Any

from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.models.log_event import LogEvent


class LogEventRepository:
    """Repository for log event persistence."""

    @staticmethod
    def insert_many_on_conflict_do_nothing(db: Session, rows: list[dict[str, Any]]) -> int:
        """Insert log events, skipping rows that violate the dedupe unique index."""
        if not rows:
            return 0

        stmt = insert(LogEvent).values(rows)
        stmt = stmt.on_conflict_do_nothing(
            index_elements=[LogEvent.app_id, LogEvent.dedupe_key],
        ).returning(LogEvent.id)
        result = db.execute(stmt)
        inserted_ids = result.fetchall()
        db.flush()
        return len(inserted_ids)
