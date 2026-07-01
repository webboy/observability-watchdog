"""Background post-processing orchestration after ingestion."""

from __future__ import annotations

import logging
import uuid

from app.database import SessionLocal
from app.repositories.ingestion_run_repository import IngestionRunRepository
from app.services.anomaly_detection_service import AnomalyDetectionService
from app.services.metrics_aggregator import MetricsAggregator
from app.services.window_utils import floor_to_window_start

logger = logging.getLogger(__name__)


def process_ingestion_run(ingestion_run_id: uuid.UUID) -> None:
    """Run metric aggregation and anomaly detection for one ingestion run."""
    db = SessionLocal()
    run_repo = IngestionRunRepository()

    try:
        run = run_repo.get_by_id(db, ingestion_run_id)
        if run is None:
            logger.warning("Ingestion run %s not found for background processing", ingestion_run_id)
            return

        aggregator = MetricsAggregator(db)
        windows = aggregator.recompute_for_ingestion_run(ingestion_run_id, run.app_id)

        bucket_starts = sorted({floor_to_window_start(window.window_start) for window in windows})
        affected_windows = aggregator.metric_repo.list_for_bucket_starts(
            db,
            app_id=run.app_id,
            window_starts=bucket_starts,
        )

        detector = AnomalyDetectionService(db)
        anomalies = detector.detect_for_windows(affected_windows)

        from app.services.incident_summary_service import IncidentSummaryService
        from app.services.alert_service import AlertService

        enriched_anomalies = IncidentSummaryService(db).enrich_anomalies(anomalies)
        alerts = AlertService(db).create_alerts_for_anomalies(run.app_id, enriched_anomalies)

        run_repo.complete_processing(
            db,
            run,
            detected_anomalies=len(enriched_anomalies),
            alerts_triggered=len(alerts),
        )
        db.commit()
    except Exception:
        db.rollback()
        logger.exception("Background processing failed for ingestion run %s", ingestion_run_id)
        try:
            run = run_repo.get_by_id(db, ingestion_run_id)
            if run is not None:
                run_repo.mark_failed(db, run)
                db.commit()
        except Exception:
            db.rollback()
            logger.exception("Failed to mark ingestion run %s as failed", ingestion_run_id)
    finally:
        db.close()
