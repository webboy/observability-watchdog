"""Dashboard and demo API routes."""

import uuid

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.api.logs import _schedule_post_processing
from app.config import get_settings
from app.database import get_db
from app.repositories.anomaly_repository import AnomalyRepository
from app.repositories.app_repository import AppRepository
from app.schemas.dashboard import (
    AnomalyListResponse,
    AnomalyRead,
    DashboardOverviewRead,
    DemoClearDataResponse,
    MetricWindowListResponse,
    MetricWindowRead,
    TopFailingServicesResponse,
)
from app.schemas.log_ingestion import IngestionResponse
from app.services.dashboard_service import DashboardService
from app.services.demo_service import DemoService
from app.services.log_ingestion_service import AppNotFoundError

router = APIRouter(prefix=get_settings().api_v1_prefix, tags=["dashboard"])
app_repo = AppRepository()
anomaly_repo = AnomalyRepository()


def _get_app_or_404(db: Session, app_id: uuid.UUID):
    app = app_repo.get_by_id(db, app_id)
    if app is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="App not found")
    return app


@router.get("/apps/{app_id}/dashboard/overview", response_model=DashboardOverviewRead)
def get_dashboard_overview(app_id: uuid.UUID, db: Session = Depends(get_db)) -> DashboardOverviewRead:
    """Return overview metrics and system health score for an app."""
    _get_app_or_404(db, app_id)
    return DashboardService(db).get_overview(app_id)


@router.get("/apps/{app_id}/dashboard/metric-windows", response_model=MetricWindowListResponse)
def list_metric_windows(
    app_id: uuid.UUID,
    limit: int = Query(default=500, ge=1, le=2000),
    db: Session = Depends(get_db),
) -> MetricWindowListResponse:
    """Return chart-ready metric windows for an app."""
    _get_app_or_404(db, app_id)
    windows = DashboardService.list_metric_windows(db, app_id, limit=limit)
    return MetricWindowListResponse(items=[MetricWindowRead.model_validate(window) for window in windows])


@router.get("/apps/{app_id}/dashboard/top-failing-services", response_model=TopFailingServicesResponse)
def get_top_failing_services(
    app_id: uuid.UUID,
    limit: int = Query(default=10, ge=1, le=50),
    db: Session = Depends(get_db),
) -> TopFailingServicesResponse:
    """Return ranked failing services for an app."""
    _get_app_or_404(db, app_id)
    items = DashboardService(db).get_top_failing_services(app_id, limit=limit)
    return TopFailingServicesResponse(items=items)


@router.get("/apps/{app_id}/dashboard/anomalies", response_model=AnomalyListResponse)
def list_dashboard_anomalies(
    app_id: uuid.UUID,
    limit: int = Query(default=50, ge=1, le=200),
    db: Session = Depends(get_db),
) -> AnomalyListResponse:
    """Return latest anomalies for dashboard tables."""
    _get_app_or_404(db, app_id)
    anomalies = anomaly_repo.list_for_app(db, app_id, limit=limit)
    return AnomalyListResponse(items=[AnomalyRead.model_validate(anomaly) for anomaly in anomalies])


@router.post(
    "/apps/{app_id}/demo/load-sample-dataset",
    response_model=IngestionResponse,
    status_code=status.HTTP_201_CREATED,
)
def load_sample_dataset(
    app_id: uuid.UUID,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
) -> IngestionResponse:
    """Load the bundled sample incident dataset for demo workflows."""
    _get_app_or_404(db, app_id)
    service = DemoService(db)
    try:
        response = service.load_sample_dataset(app_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except AppNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc

    _schedule_post_processing(background_tasks, response)
    return response


@router.post("/apps/{app_id}/demo/clear-data", response_model=DemoClearDataResponse)
def clear_app_data(app_id: uuid.UUID, db: Session = Depends(get_db)) -> DemoClearDataResponse:
    """Clear dynamic app data while preserving the App record."""
    _get_app_or_404(db, app_id)
    service = DemoService(db)
    try:
        return service.clear_app_data(app_id)
    except AppNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
