"""Dashboard response schemas."""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class DashboardOverviewRead(BaseModel):
    """Overview metrics for the selected app."""

    total_logs: int
    accepted_events: int
    rejected_events: int
    skipped_duplicates: int
    active_anomalies: int
    triggered_alerts: int
    system_health_score: int
    latest_log_timestamp: datetime | None
    critical_anomalies_24h: int
    warning_anomalies_24h: int


class MetricWindowRead(BaseModel):
    """Chart-ready metric window row."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    service_name: str
    url_path: str | None
    window_start: datetime
    window_end: datetime
    total_events: int
    error_count: int
    error_rate: float
    http_5xx_count: int
    http_5xx_rate: float
    latency_p95_ms: float | None
    most_common_error_type: str | None


class MetricWindowListResponse(BaseModel):
    """List of metric windows for health trend charts."""

    items: list[MetricWindowRead] = Field(default_factory=list)


class TopFailingServiceRead(BaseModel):
    """Ranked failing service summary."""

    rank: int
    service_name: str
    total_events: int
    error_count: int
    http_5xx_count: int
    avg_error_rate: float
    max_p95_latency_ms: float | None
    failure_score: float


class TopFailingServicesResponse(BaseModel):
    """Ranked list of top failing services."""

    items: list[TopFailingServiceRead] = Field(default_factory=list)


class AnomalyRead(BaseModel):
    """Dashboard anomaly row."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    service_name: str
    url_path: str | None
    severity: str
    metric_name: str
    window_start: datetime
    window_end: datetime
    observed_value: float
    baseline_value: float
    anomaly_score: float
    reason: str
    created_at: datetime


class AnomalyListResponse(BaseModel):
    """List of detected anomalies."""

    items: list[AnomalyRead] = Field(default_factory=list)


class DemoClearDataResponse(BaseModel):
    """Response after clearing app-scoped dynamic data."""

    app_id: UUID
    deleted_log_events: int
    deleted_metric_windows: int
    deleted_ingestion_runs: int
    deleted_anomalies: int
    deleted_alerts: int
