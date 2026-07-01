"""Log ingestion request and response schemas."""

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class LogEventsRequest(BaseModel):
    """Batch of raw ECS-compatible log events."""

    events: list[dict[str, Any]] = Field(..., min_length=1)


class IngestionRunRead(BaseModel):
    """Serialized ingestion run counters."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    app_id: UUID
    source_type: str
    source_name: str | None
    filename: str | None
    total_lines: int
    accepted_events: int
    rejected_events: int
    skipped_duplicates: int
    detected_anomalies: int
    alerts_triggered: int
    status: str
    created_at: datetime
    completed_at: datetime | None


class IngestionResponse(BaseModel):
    """Response returned after request-time ingestion."""

    ingestion_run_id: UUID
    filename: str | None = None
    total_lines: int
    accepted_events: int
    rejected_events: int
    skipped_duplicates: int
    detected_anomalies: int = 0
    alerts_triggered: int = 0
    status: str


class ValidationErrorDetail(BaseModel):
    """Single validation failure for a submitted event."""

    index: int
    message: str


class ValidationWarningDetail(BaseModel):
    """Non-fatal validation warning for a submitted event."""

    index: int
    message: str


class ValidationResponse(BaseModel):
    """Dry-run validation response without persistence."""

    total_events: int
    valid_events: int
    rejected_events: int
    errors: list[ValidationErrorDetail] = Field(default_factory=list)
    warnings: list[ValidationWarningDetail] = Field(default_factory=list)
