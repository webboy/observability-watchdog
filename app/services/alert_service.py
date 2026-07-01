"""Simulated webhook alert creation service."""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy.orm import Session

from app.models.alert import Alert
from app.models.anomaly import Anomaly
from app.models.app import App
from app.repositories.alert_repository import AlertRepository
from app.repositories.app_repository import AppRepository

ALERT_SEVERITIES = {"WARNING", "CRITICAL"}


class AlertService:
    """Create simulated webhook alerts from detected anomalies."""

    def __init__(self, db: Session) -> None:
        self.db = db
        self.alert_repo = AlertRepository()
        self.app_repo = AppRepository()

    def create_alerts_for_anomalies(
        self,
        app_id: uuid.UUID,
        anomalies: list[Anomaly],
    ) -> list[Alert]:
        """Create or refresh simulated alerts for warning/critical anomalies."""
        app = self.app_repo.get_by_id(self.db, app_id)
        app_name = app.name if app else str(app_id)

        alerts: list[Alert] = []
        for anomaly in anomalies:
            if anomaly.severity not in ALERT_SEVERITIES:
                continue

            payload = self._build_payload(app_id=app_id, app_name=app_name, anomaly=anomaly)
            alert = self.alert_repo.upsert_for_anomaly(
                self.db,
                {
                    "app_id": app_id,
                    "anomaly_id": anomaly.id,
                    "severity": anomaly.severity,
                    "delivery_status": "simulated",
                    "webhook_payload": payload,
                },
            )
            alerts.append(alert)
        return alerts

    @staticmethod
    def _build_payload(*, app_id: uuid.UUID, app_name: str, anomaly: Anomaly) -> dict[str, Any]:
        endpoint = anomaly.url_path or anomaly.service_name
        message = f"{anomaly.severity.title()} {anomaly.metric_name} anomaly detected in {anomaly.service_name}"
        return {
            "event_type": "anomaly.detected",
            "severity": anomaly.severity,
            "app_id": str(app_id),
            "app": app_name,
            "anomaly_id": str(anomaly.id),
            "service_name": anomaly.service_name,
            "service": anomaly.service_name,
            "url_path": anomaly.url_path,
            "endpoint": endpoint,
            "metric_name": anomaly.metric_name,
            "observed_value": anomaly.observed_value,
            "baseline_value": anomaly.baseline_value,
            "anomaly_score": anomaly.anomaly_score,
            "message": message,
            "reason": anomaly.reason,
            "likely_cause": anomaly.likely_cause,
            "recommended_action": anomaly.recommended_action,
            "delivery_status": "simulated",
        }
