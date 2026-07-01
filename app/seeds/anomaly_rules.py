"""Seed default global anomaly detection rules."""

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.anomaly_rule import AnomalyRule

DEFAULT_RULES = [
    {
        "name": "Error count spike",
        "metric_name": "error_count",
        "window_minutes": 10,
        "baseline_window_minutes": 60,
        "warning_multiplier": 3.0,
        "critical_multiplier": 8.0,
        "min_event_count": 10,
    },
    {
        "name": "HTTP 5xx rate spike",
        "metric_name": "http_5xx_rate",
        "window_minutes": 10,
        "baseline_window_minutes": 60,
        "warning_multiplier": 2.0,
        "critical_multiplier": 5.0,
        "min_event_count": 20,
    },
    {
        "name": "Latency p95 spike",
        "metric_name": "latency_p95",
        "window_minutes": 10,
        "baseline_window_minutes": 60,
        "warning_multiplier": 2.0,
        "critical_multiplier": 4.0,
        "min_event_count": 20,
    },
]


def seed_default_anomaly_rules(db: Session) -> None:
    """Insert global default anomaly rules when none exist."""
    count = db.scalar(
        select(func.count()).select_from(AnomalyRule).where(AnomalyRule.app_id.is_(None))
    )
    if count and count > 0:
        return

    for rule in DEFAULT_RULES:
        db.add(AnomalyRule(app_id=None, enabled=True, **rule))
    db.commit()
