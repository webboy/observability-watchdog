"""Ingestion run entity tracking one log upload or batch submission."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, Integer, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from app.models.app import App
    from app.models.log_event import LogEvent


class IngestionRun(Base, UUIDPrimaryKeyMixin):
    """Represents one ingestion attempt for an app."""

    __tablename__ = "ingestion_runs"

    app_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("apps.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    source_type: Mapped[str] = mapped_column(String(50), nullable=False)
    source_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    filename: Mapped[str | None] = mapped_column(String(255), nullable=True)
    total_lines: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    accepted_events: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    rejected_events: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    skipped_duplicates: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    detected_anomalies: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    alerts_triggered: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    status: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        default="processing",
        server_default="processing",
        index=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default="now()",
        nullable=False,
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    app: Mapped[App] = relationship("App", back_populates="ingestion_runs")
    log_events: Mapped[list[LogEvent]] = relationship(
        "LogEvent",
        back_populates="ingestion_run",
        cascade="all, delete-orphan",
    )
