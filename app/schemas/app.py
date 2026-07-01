"""App request and response schemas."""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class AppCreate(BaseModel):
    """Payload for creating a monitored application."""

    name: str = Field(..., min_length=1, max_length=255)
    slug: str = Field(..., min_length=1, max_length=255, pattern=r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
    description: str | None = None
    environment: str = Field(default="production", max_length=100)


class AppRead(BaseModel):
    """Serialized app entity."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
    slug: str
    description: str | None
    environment: str
    created_at: datetime
    updated_at: datetime


class AppListResponse(BaseModel):
    """List of monitored applications."""

    items: list[AppRead]
