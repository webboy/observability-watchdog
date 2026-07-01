"""Alert and incident summary API routes."""

import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.config import get_settings
from app.database import get_db
from app.repositories.alert_repository import AlertRepository
from app.repositories.anomaly_repository import AnomalyRepository
from app.repositories.app_repository import AppRepository
from app.schemas.alert import AlertListResponse, AlertRead
from app.schemas.incident import IncidentSummaryResponse
from app.services.incident_summary_service import IncidentSummaryService

router = APIRouter(prefix=get_settings().api_v1_prefix, tags=["alerts"])
app_repo = AppRepository()
alert_repo = AlertRepository()
anomaly_repo = AnomalyRepository()


def _get_app_or_404(db: Session, app_id: uuid.UUID):
    app = app_repo.get_by_id(db, app_id)
    if app is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="App not found")
    return app


@router.get("/apps/{app_id}/alerts", response_model=AlertListResponse)
def list_alerts(
    app_id: uuid.UUID,
    limit: int = Query(default=50, ge=1, le=200),
    severity: str | None = None,
    service_name: str | None = None,
    db: Session = Depends(get_db),
) -> AlertListResponse:
    """List simulated webhook alerts for an app."""
    _get_app_or_404(db, app_id)
    alerts = alert_repo.list_for_app(
        db,
        app_id,
        limit=limit,
        severity=severity,
        service_name=service_name,
    )
    return AlertListResponse(items=[AlertRead.model_validate(alert) for alert in alerts])


@router.get("/apps/{app_id}/incidents/summary", response_model=IncidentSummaryResponse)
def get_incident_summaries(
    app_id: uuid.UUID,
    limit: int = Query(default=10, ge=1, le=50),
    db: Session = Depends(get_db),
) -> IncidentSummaryResponse:
    """Return latest incident summaries derived from enriched anomalies."""
    _get_app_or_404(db, app_id)
    anomalies = anomaly_repo.list_for_app(
        db,
        app_id,
        limit=limit,
        severities=["CRITICAL", "WARNING"],
    )

    items = [
        IncidentSummaryService.build_summary_read(anomaly)
        for anomaly in anomalies
        if anomaly.ai_summary
    ]
    return IncidentSummaryResponse(items=items)
