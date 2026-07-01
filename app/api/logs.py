"""Log ingestion API routes."""

import uuid

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from sqlalchemy.orm import Session

from app.config import get_settings
from app.database import get_db
from app.schemas.log_ingestion import IngestionResponse, LogEventsRequest, ValidationResponse
from app.services.log_ingestion_service import AppNotFoundError, LogIngestionService

router = APIRouter(prefix=get_settings().api_v1_prefix, tags=["logs"])


@router.post(
    "/apps/{app_id}/logs/upload",
    response_model=IngestionResponse,
    status_code=status.HTTP_201_CREATED,
)
async def upload_logs(
    app_id: uuid.UUID,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
) -> IngestionResponse:
    """Upload an ECS-compatible JSONL file for ingestion."""
    service = LogIngestionService(db)
    try:
        return service.ingest_upload(app_id, file)
    except AppNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


@router.post(
    "/apps/{app_id}/logs/events",
    response_model=IngestionResponse,
    status_code=status.HTTP_201_CREATED,
)
def ingest_events(
    app_id: uuid.UUID,
    payload: LogEventsRequest,
    db: Session = Depends(get_db),
) -> IngestionResponse:
    """Ingest a JSON batch of ECS-compatible log events."""
    service = LogIngestionService(db)
    try:
        return service.ingest_events(app_id, payload)
    except AppNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


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
