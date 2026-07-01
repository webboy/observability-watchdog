"""Demo utility operations for sample dataset loading and app data clearing."""

from __future__ import annotations

import uuid
from pathlib import Path

from fastapi import UploadFile
from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from app.models.alert import Alert
from app.models.anomaly import Anomaly
from app.models.ingestion_run import IngestionRun
from app.models.log_event import LogEvent
from app.models.metric_window import MetricWindow
from app.repositories.app_repository import AppRepository
from app.schemas.dashboard import DemoClearDataResponse
from app.schemas.log_ingestion import IngestionResponse
from app.services.log_ingestion_service import AppNotFoundError, LogIngestionService

SAMPLE_INCIDENT_PATH = Path("data/sample_incident_logs.jsonl")


class DemoService:
    """Demo helpers for reviewer workflows."""

    def __init__(self, db: Session) -> None:
        self.db = db
        self.app_repo = AppRepository()
        self.ingestion_service = LogIngestionService(db)

    def load_sample_dataset(self, app_id: uuid.UUID) -> IngestionResponse:
        """Ingest the bundled sample incident JSONL file for an app."""
        if self.app_repo.get_by_id(self.db, app_id) is None:
            raise AppNotFoundError(f"App '{app_id}' not found")
        if not SAMPLE_INCIDENT_PATH.exists():
            raise FileNotFoundError(f"Sample dataset not found at {SAMPLE_INCIDENT_PATH}")

        with SAMPLE_INCIDENT_PATH.open("rb") as handle:
            upload = UploadFile(filename=SAMPLE_INCIDENT_PATH.name, file=handle)
            return self.ingestion_service.ingest_upload(app_id, upload)

    def clear_app_data(self, app_id: uuid.UUID) -> DemoClearDataResponse:
        """Delete dynamic app-scoped data while preserving the App record."""
        if self.app_repo.get_by_id(self.db, app_id) is None:
            raise AppNotFoundError(f"App '{app_id}' not found")

        deleted_alerts = self._count_for_app(Alert, app_id)
        deleted_anomalies = self._count_for_app(Anomaly, app_id)
        deleted_metric_windows = self._count_for_app(MetricWindow, app_id)
        deleted_log_events = self._count_for_app(LogEvent, app_id)
        deleted_ingestion_runs = self._count_for_app(IngestionRun, app_id)

        self.db.execute(delete(Alert).where(Alert.app_id == app_id))
        self.db.execute(delete(Anomaly).where(Anomaly.app_id == app_id))
        self.db.execute(delete(MetricWindow).where(MetricWindow.app_id == app_id))
        self.db.execute(delete(LogEvent).where(LogEvent.app_id == app_id))
        self.db.execute(delete(IngestionRun).where(IngestionRun.app_id == app_id))
        self.db.commit()

        return DemoClearDataResponse(
            app_id=app_id,
            deleted_log_events=deleted_log_events,
            deleted_metric_windows=deleted_metric_windows,
            deleted_ingestion_runs=deleted_ingestion_runs,
            deleted_anomalies=deleted_anomalies,
            deleted_alerts=deleted_alerts,
        )

    def _count_for_app(self, model, app_id: uuid.UUID) -> int:
        return self.db.scalar(select(func.count()).select_from(model).where(model.app_id == app_id)) or 0
