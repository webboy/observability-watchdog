"""Data access helpers for Alert entities."""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.alert import Alert


class AlertRepository:
    """Repository for simulated alert persistence."""

    @staticmethod
    def upsert_for_anomaly(db: Session, row: dict[str, Any]) -> Alert:
        """Insert or update one alert keyed by anomaly_id."""
        existing = db.scalar(select(Alert).where(Alert.anomaly_id == row["anomaly_id"]))
        if existing:
            for key, value in row.items():
                setattr(existing, key, value)
            db.flush()
            return existing

        alert = Alert(**row)
        db.add(alert)
        db.flush()
        return alert

    @staticmethod
    def list_for_app(
        db: Session,
        app_id: uuid.UUID,
        *,
        limit: int = 50,
        severity: str | None = None,
        service_name: str | None = None,
    ) -> list[Alert]:
        """Return latest alerts for an app."""
        stmt = select(Alert).where(Alert.app_id == app_id)
        if severity:
            stmt = stmt.where(Alert.severity == severity.upper())
        if service_name:
            stmt = stmt.where(Alert.webhook_payload["service_name"].astext == service_name)
        stmt = stmt.order_by(Alert.created_at.desc()).limit(limit)
        return list(db.scalars(stmt).all())
