"""Health check endpoints."""

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.config import get_settings
from app.database import check_database_connection, get_db

router = APIRouter(tags=["health"])
settings = get_settings()


class HealthResponse(BaseModel):
    """Basic application health response."""

    status: str
    app_name: str
    environment: str


class DetailedHealthResponse(HealthResponse):
    """Health response including database connectivity."""

    database: str


@router.get("/health", response_model=HealthResponse)
def health_check() -> HealthResponse:
    """Return basic application health."""
    return HealthResponse(
        status="ok",
        app_name=settings.app_name,
        environment=settings.environment,
    )


@router.get(f"{settings.api_v1_prefix}/health", response_model=DetailedHealthResponse)
def detailed_health_check(db: Session = Depends(get_db)) -> DetailedHealthResponse:
    """Return application health with database connectivity status."""
    del db  # session dependency ensures DB is reachable for connection pool
    try:
        check_database_connection()
        database_status = "connected"
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Database unavailable: {exc}",
        ) from exc

    return DetailedHealthResponse(
        status="ok",
        app_name=settings.app_name,
        environment=settings.environment,
        database=database_status,
    )
