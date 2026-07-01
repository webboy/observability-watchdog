"""Simulated webhook alert entity."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, ForeignKey, Index, String, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, UUIDPrimaryKeyMixin


class Alert(Base, UUIDPrimaryKeyMixin):
    """Represents a simulated webhook alert created from an anomaly."""

    __tablename__ = "alerts"
    __table_args__ = (
        Index("idx_alerts_app_created", "app_id", "created_at"),
        Index("idx_alerts_app_severity_created", "app_id", "severity", "created_at"),
        Index("uq_alerts_anomaly_id", "anomaly_id", unique=True),
    )

    app_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("apps.id", ondelete="CASCADE"),
        nullable=False,
    )
    anomaly_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("anomalies.id", ondelete="CASCADE"),
        nullable=False,
    )
    severity: Mapped[str] = mapped_column(String(20), nullable=False)
    delivery_status: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        default="simulated",
        server_default="simulated",
    )
    webhook_payload: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
