"""Data access helpers for Anomaly entities."""

from __future__ import annotations

from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.anomaly import Anomaly


class AnomalyRepository:
    """Repository for anomaly persistence."""

    @staticmethod
    def upsert(db: Session, row: dict[str, Any]) -> Anomaly:
        """Insert or update one anomaly for a unique scope."""
        existing = db.scalar(
            select(Anomaly).where(
                Anomaly.app_id == row["app_id"],
                Anomaly.rule_id == row["rule_id"],
                Anomaly.service_name == row["service_name"],
                func.coalesce(Anomaly.url_path, "") == (row.get("url_path") or ""),
                Anomaly.window_start == row["window_start"],
                Anomaly.metric_name == row["metric_name"],
            )
        )
        if existing:
            for key, value in row.items():
                setattr(existing, key, value)
            db.flush()
            return existing

        anomaly = Anomaly(**row)
        db.add(anomaly)
        db.flush()
        return anomaly

    @staticmethod
    def delete_non_anomalous_for_window(
        db: Session,
        *,
        app_id,
        service_name: str,
        url_path: str | None,
        window_start,
        metric_name: str,
    ) -> None:
        """Remove stale anomaly rows when a window returns to normal."""
        existing = db.scalar(
            select(Anomaly).where(
                Anomaly.app_id == app_id,
                Anomaly.service_name == service_name,
                func.coalesce(Anomaly.url_path, "") == (url_path or ""),
                Anomaly.window_start == window_start,
                Anomaly.metric_name == metric_name,
            )
        )
        if existing is not None:
            db.delete(existing)

    @staticmethod
    def list_for_app(
        db: Session,
        app_id,
        *,
        limit: int = 50,
        severities: list[str] | None = None,
    ) -> list[Anomaly]:
        """Return latest anomalies for an app ordered by window start."""
        stmt = select(Anomaly).where(Anomaly.app_id == app_id)
        if severities:
            stmt = stmt.where(Anomaly.severity.in_(severities))
        stmt = stmt.order_by(Anomaly.window_start.desc(), Anomaly.created_at.desc()).limit(limit)
        return list(db.scalars(stmt).all())

    @staticmethod
    def update_summary_fields(
        db: Session,
        anomaly: Anomaly,
        *,
        ai_summary: str,
        likely_cause: str | None,
        business_impact: str | None,
        recommended_action: str | None,
        generation_source: str,
    ) -> Anomaly:
        """Persist incident intelligence fields on an anomaly."""
        anomaly.ai_summary = ai_summary
        anomaly.likely_cause = likely_cause
        anomaly.business_impact = business_impact
        anomaly.recommended_action = recommended_action
        anomaly.generation_source = generation_source
        db.add(anomaly)
        db.flush()
        return anomaly
