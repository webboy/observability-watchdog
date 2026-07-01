"""Data access helpers for AnomalyRule entities."""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.anomaly_rule import AnomalyRule


class AnomalyRuleRepository:
    """Repository for anomaly rule resolution."""

    @staticmethod
    def resolve_rule(db: Session, app_id: uuid.UUID, metric_name: str) -> AnomalyRule | None:
        """Resolve app-specific rule first, then global default."""
        app_rule = db.scalar(
            select(AnomalyRule).where(
                AnomalyRule.app_id == app_id,
                AnomalyRule.metric_name == metric_name,
                AnomalyRule.enabled.is_(True),
            )
        )
        if app_rule is not None:
            return app_rule

        return db.scalar(
            select(AnomalyRule).where(
                AnomalyRule.app_id.is_(None),
                AnomalyRule.metric_name == metric_name,
                AnomalyRule.enabled.is_(True),
            )
        )
