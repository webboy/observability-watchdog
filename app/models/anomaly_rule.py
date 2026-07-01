"""Anomaly detection rule configuration entity."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, String, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, UUIDPrimaryKeyMixin


class AnomalyRule(Base, UUIDPrimaryKeyMixin):
    """Guardrail configuration for baseline anomaly detection."""

    __tablename__ = "anomaly_rules"

    app_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("apps.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    metric_name: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    window_minutes: Mapped[int] = mapped_column(Integer, nullable=False, default=10, server_default="10")
    baseline_window_minutes: Mapped[int] = mapped_column(Integer, nullable=False, default=60, server_default="60")
    warning_multiplier: Mapped[float] = mapped_column(Float, nullable=False)
    critical_multiplier: Mapped[float] = mapped_column(Float, nullable=False)
    min_event_count: Mapped[int] = mapped_column(Integer, nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default="true")
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
