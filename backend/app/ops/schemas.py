from datetime import datetime

from pydantic import BaseModel, Field


class OpsCountSummary(BaseModel):
    total_count: int = Field(ge=0)
    status_counts: dict[str, int] = Field(default_factory=dict)
    unhealthy_count: int = Field(default=0, ge=0)
    latest_status: str | None = None
    latest_at: datetime | None = None


class OpsRadarSummary(BaseModel):
    latest_scan_id: int | None = None
    latest_scan_status: str | None = None
    latest_scan_started_at: datetime | None = None
    latest_scan_finished_at: datetime | None = None
    latest_scan_duration_seconds: float | None = None
    latest_scan_age_seconds: float | None = None
    scan_interval_seconds: int = Field(gt=0)
    is_latest_scan_stale: bool
    recent_scan_count: int = Field(ge=0)
    recent_scan_failure_count: int = Field(ge=0)
    recent_scan_failure_rate: float = Field(ge=0, le=1)
    status_counts: dict[str, int] = Field(default_factory=dict)


class OpsAlertRead(BaseModel):
    severity: str
    code: str
    message: str


class OpsOverviewRead(BaseModel):
    generated_at: datetime
    lookback_hours: int = Field(ge=1, le=168)
    radar: OpsRadarSummary
    provider_fetch: OpsCountSummary
    data_quality: OpsCountSummary
    telegram_push: OpsCountSummary
    model_calls: OpsCountSummary
    alerts: list[OpsAlertRead] = Field(default_factory=list)
