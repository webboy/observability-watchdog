"""Parsed log event entity."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy import BigInteger, DateTime, ForeignKey, Index, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from app.models.app import App
    from app.models.ingestion_run import IngestionRun


class LogEvent(Base, UUIDPrimaryKeyMixin):
    """Represents one valid parsed ECS-compatible log event."""

    __tablename__ = "log_events"
    __table_args__ = (
        Index("uq_log_events_app_dedupe", "app_id", "dedupe_key", unique=True),
        Index("idx_log_events_app_timestamp", "app_id", "timestamp"),
        Index("idx_log_events_app_service_timestamp", "app_id", "service_name", "timestamp"),
        Index("idx_log_events_app_level_timestamp", "app_id", "log_level", "timestamp"),
        Index("idx_log_events_raw_json", "raw_event_json", postgresql_using="gin"),
    )

    app_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("apps.id", ondelete="CASCADE"),
        nullable=False,
    )
    ingestion_run_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("ingestion_runs.id", ondelete="CASCADE"),
        nullable=False,
    )
    event_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    dedupe_key: Mapped[str] = mapped_column(String(128), nullable=False)
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    service_name: Mapped[str] = mapped_column(String(255), nullable=False)
    log_level: Mapped[str] = mapped_column(String(50), nullable=False)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    event_dataset: Mapped[str | None] = mapped_column(String(255), nullable=True)
    event_outcome: Mapped[str | None] = mapped_column(String(100), nullable=True)
    event_duration_ns: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    http_status_code: Mapped[int | None] = mapped_column(Integer, nullable=True)
    url_path: Mapped[str | None] = mapped_column(Text, nullable=True)
    trace_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    span_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    transaction_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    error_type: Mapped[str | None] = mapped_column(String(255), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    raw_event_json: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    app: Mapped[App] = relationship("App", back_populates="log_events")
    ingestion_run: Mapped[IngestionRun] = relationship("IngestionRun", back_populates="log_events")
