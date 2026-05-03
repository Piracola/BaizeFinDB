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
    cpu_logical_count: int | None = Field(default=None, ge=0)
    cpu_usage_percent: float | None = Field(default=None, ge=0, le=100)
    cpu_load_1m: float | None = Field(default=None, ge=0)
    cpu_load_5m: float | None = Field(default=None, ge=0)
    cpu_load_15m: float | None = Field(default=None, ge=0)
    is_cpu_pressure_high: bool
    cpu_error: str | None = None
    memory_total_bytes: int | None = Field(default=None, ge=0)
    memory_available_bytes: int | None = Field(default=None, ge=0)
    memory_used_bytes: int | None = Field(default=None, ge=0)
    memory_used_percent: float | None = Field(default=None, ge=0, le=100)
    memory_available_percent: float | None = Field(default=None, ge=0, le=100)
    is_memory_pressure_high: bool
    memory_error: str | None = None


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


class OpsHistoryEventRead(BaseModel):
    id: int = Field(ge=0)
    kind: str
    status: str
    occurred_at: datetime
    duration_seconds: float | None = Field(default=None, ge=0)
    title: str
    detail: str | None = None
    metadata: dict[str, object] = Field(default_factory=dict)


class OpsFailureSummaryRead(BaseModel):
    kind: str
    key: str
    count: int = Field(ge=0)


class OpsHistoryRead(BaseModel):
    generated_at: datetime
    lookback_hours: int = Field(ge=1, le=168)
    limit: int = Field(ge=1, le=100)
    recent_events: list[OpsHistoryEventRead] = Field(default_factory=list)
    failure_summary: list[OpsFailureSummaryRead] = Field(default_factory=list)


class OpsReadinessCheckRead(BaseModel):
    name: str
    status: str
    message: str
    metadata: dict[str, object] = Field(default_factory=dict)


class OpsReadinessRead(BaseModel):
    generated_at: datetime
    lookback_hours: int = Field(ge=1, le=168)
    status: str
    checks: list[OpsReadinessCheckRead] = Field(default_factory=list)
