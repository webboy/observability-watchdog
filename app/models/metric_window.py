"""Pre-aggregated metric window entity."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, Float, Index, Integer, String, Text, func, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, UUIDPrimaryKeyMixin


class MetricWindow(Base, UUIDPrimaryKeyMixin):
    """Aggregated metrics for one fixed time bucket and scope."""

    __tablename__ = "metric_windows"
    __table_args__ = (
        Index(
            "uq_metric_windows_scope",
            "app_id",
            "service_name",
            text("COALESCE(url_path, '')"),
            "window_start",
            "window_minutes",
            unique=True,
        ),
        Index("idx_metric_windows_app_window", "app_id", "window_start"),
        Index("idx_metric_windows_app_service_window", "app_id", "service_name", "window_start"),
    )

    app_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        nullable=False,
        index=True,
    )
    service_name: Mapped[str] = mapped_column(String(255), nullable=False)
    url_path: Mapped[str | None] = mapped_column(Text, nullable=True)
    window_start: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    window_end: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    window_minutes: Mapped[int] = mapped_column(Integer, nullable=False, default=10, server_default="10")
    total_events: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    error_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    error_rate: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    http_5xx_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    http_5xx_rate: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    latency_p95_ms: Mapped[float | None] = mapped_column(Float, nullable=True)
    unique_error_types: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    most_common_error_type: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )
