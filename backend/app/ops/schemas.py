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


class OpsServerSummary(BaseModel):
    process_id: int = Field(ge=0)
    process_started_at: datetime
    process_uptime_seconds: float = Field(ge=0)
    python_version: str
    platform: str
    disk_path: str
    disk_total_bytes: int | None = Field(default=None, ge=0)
    disk_used_bytes: int | None = Field(default=None, ge=0)
    disk_free_bytes: int | None = Field(default=None, ge=0)
    disk_used_percent: float | None = Field(default=None, ge=0, le=100)
    disk_free_percent: float | None = Field(default=None, ge=0, le=100)
    is_disk_space_low: bool
    disk_error: str | None = None


class OpsOverviewRead(BaseModel):
    generated_at: datetime
    lookback_hours: int = Field(ge=1, le=168)
    server: OpsServerSummary
    radar: OpsRadarSummary
    provider_fetch: OpsCountSummary
    data_quality: OpsCountSummary
    telegram_push: OpsCountSummary
    model_calls: OpsCountSummary
    alerts: list[OpsAlertRead] = Field(default_factory=list)
