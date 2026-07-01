"""Monitored application entity."""

from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from app.models.ingestion_run import IngestionRun
    from app.models.log_event import LogEvent


class App(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """Represents a monitored application or platform."""

    __tablename__ = "apps"

    name: Mapped[str] = mapped_column(String(255), nullable=False)
    slug: Mapped[str] = mapped_column(String(255), nullable=False, unique=True, index=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    environment: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
        default="production",
        server_default="production",
    )

    ingestion_runs: Mapped[list[IngestionRun]] = relationship(
        "IngestionRun",
        back_populates="app",
        cascade="all, delete-orphan",
    )
    log_events: Mapped[list[LogEvent]] = relationship(
        "LogEvent",
        back_populates="app",
        cascade="all, delete-orphan",
    )
