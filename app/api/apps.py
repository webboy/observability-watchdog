"""App CRUD API routes."""

import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.config import get_settings
from app.database import get_db
from app.repositories.app_repository import AppRepository
from app.schemas.app import AppCreate, AppListResponse, AppRead

router = APIRouter(prefix=get_settings().api_v1_prefix, tags=["apps"])
app_repo = AppRepository()


@router.post("/apps", response_model=AppRead, status_code=status.HTTP_201_CREATED)
def create_app(payload: AppCreate, db: Session = Depends(get_db)) -> AppRead:
    """Create a monitored application."""
    try:
        app = app_repo.create(db, payload)
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"App with slug '{payload.slug}' already exists",
        ) from exc
    return AppRead.model_validate(app)


@router.get("/apps", response_model=AppListResponse)
def list_apps(db: Session = Depends(get_db)) -> AppListResponse:
    """List all monitored applications."""
    apps = app_repo.list_all(db)
    return AppListResponse(items=[AppRead.model_validate(app) for app in apps])


@router.get("/apps/{app_id}", response_model=AppRead)
def get_app(app_id: uuid.UUID, db: Session = Depends(get_db)) -> AppRead:
    """Fetch one monitored application."""
    app = app_repo.get_by_id(db, app_id)
    if app is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="App not found")
    return AppRead.model_validate(app)


@router.delete("/apps/{app_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_app(app_id: uuid.UUID, db: Session = Depends(get_db)) -> None:
    """Delete a monitored application."""
    app = app_repo.get_by_id(db, app_id)
    if app is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="App not found")
    app_repo.delete(db, app)
