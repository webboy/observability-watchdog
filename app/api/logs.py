"""Log ingestion API routes."""

import uuid

from fastapi import APIRouter, BackgroundTasks, Depends, File, HTTPException, UploadFile, status
from sqlalchemy.orm import Session

from app.config import get_settings
from app.database import get_db
from app.repositories.ingestion_run_repository import IngestionRunRepository
from app.schemas.log_ingestion import IngestionResponse, IngestionRunRead, LogEventsRequest, ValidationResponse
from app.services.background_processing_service import process_ingestion_run
from app.services.log_ingestion_service import AppNotFoundError, LogIngestionService

router = APIRouter(prefix=get_settings().api_v1_prefix, tags=["logs"])
run_repo = IngestionRunRepository()


def _schedule_post_processing(background_tasks: BackgroundTasks, response: IngestionResponse) -> None:
    """Schedule background metric aggregation and anomaly detection."""
    if response.accepted_events > 0 and response.status == "processing":
        background_tasks.add_task(process_ingestion_run, response.ingestion_run_id)


@router.post(
    "/apps/{app_id}/logs/upload",
    response_model=IngestionResponse,
    status_code=status.HTTP_201_CREATED,
)
async def upload_logs(
    app_id: uuid.UUID,
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
) -> IngestionResponse:
    """Upload an ECS-compatible JSONL file for ingestion."""
    service = LogIngestionService(db)
    try:
        response = service.ingest_upload(app_id, file)
    except AppNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc

    _schedule_post_processing(background_tasks, response)
    return response


@router.post(
    "/apps/{app_id}/logs/events",
    response_model=IngestionResponse,
    status_code=status.HTTP_201_CREATED,
)
def ingest_events(
    app_id: uuid.UUID,
    background_tasks: BackgroundTasks,
    payload: LogEventsRequest,
    db: Session = Depends(get_db),
) -> IngestionResponse:
    """Ingest a JSON batch of ECS-compatible log events."""
    service = LogIngestionService(db)
    try:
        response = service.ingest_events(app_id, payload)
    except AppNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc

    _schedule_post_processing(background_tasks, response)
    return response


@router.post("/apps/{app_id}/logs/validate", response_model=ValidationResponse)
def validate_events(
    app_id: uuid.UUID,
    payload: LogEventsRequest,
    db: Session = Depends(get_db),
) -> ValidationResponse:
    """Validate ECS-compatible events without persisting them."""
    service = LogIngestionService(db)
    try:
        return service.validate_events(app_id, payload)
    except AppNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


@router.get("/apps/{app_id}/ingestion-runs/{ingestion_run_id}", response_model=IngestionRunRead)
def get_ingestion_run(
    app_id: uuid.UUID,
    ingestion_run_id: uuid.UUID,
    db: Session = Depends(get_db),
) -> IngestionRunRead:
    """Fetch ingestion run status and counters for polling."""
    run = run_repo.get_by_id(db, ingestion_run_id)
    if run is None or run.app_id != app_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Ingestion run not found")
    return IngestionRunRead.model_validate(run)
