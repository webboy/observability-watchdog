"""Alert response schemas."""

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class AlertRead(BaseModel):
    """Serialized alert entity."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    app_id: UUID
    anomaly_id: UUID
    severity: str
    delivery_status: str
    webhook_payload: dict[str, Any]
    created_at: datetime


class AlertListResponse(BaseModel):
    """List of alerts for an app."""

    items: list[AlertRead] = Field(default_factory=list)
