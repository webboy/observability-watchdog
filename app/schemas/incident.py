"""Incident summary response schemas."""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class IncidentSummaryRead(BaseModel):
    """Incident summary derived from an enriched anomaly."""

    model_config = ConfigDict(from_attributes=True)

    anomaly_id: UUID
    app_id: UUID
    service_name: str
    url_path: str | None
    severity: str
    metric_name: str
    window_start: datetime
    window_end: datetime
    summary: str
    what_happened: str | None = None
    likely_cause: str | None = None
    business_impact: str | None = None
    recommended_action: str | None = None


class IncidentSummaryResponse(BaseModel):
    """Latest incident summaries for an app."""

    items: list[IncidentSummaryRead] = Field(default_factory=list)
