from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field


class ProviderStatus(StrEnum):
    SUCCESS = "success"
    FAILURE = "failure"


class DataQualityStatus(StrEnum):
    OK = "ok"
    DEGRADED = "degraded"
    FAILED = "failed"


class DataQuality(BaseModel):
    status: DataQualityStatus
    confidence: float = Field(ge=0, le=1)
    freshness: str
    missing_fields: list[str] = Field(default_factory=list)


class ProviderDataset(BaseModel):
    provider_name: str
    endpoint: str
    market: str
    snapshot_type: str
    source_time: datetime | None = None
    collected_at: datetime
    row_count: int
    raw_summary: dict[str, object]
    normalized_rows: list[dict[str, object]]
    normalization_version: str
    quality: DataQuality


class ProviderEndpointInfo(BaseModel):
    endpoint: str
    title: str
    market: str
    snapshot_type: str
    required_fields: list[str]


class ProviderEndpointResult(BaseModel):
    endpoint: str
    status: ProviderStatus
    row_count: int = 0
    quality_status: DataQualityStatus
    confidence: float = Field(ge=0, le=1)
    missing_fields: list[str] = Field(default_factory=list)
    fetch_log_id: int | None = None
    snapshot_id: int | None = None
    error_message: str | None = None


class AkshareCollectionResponse(BaseModel):
    provider_name: str = "akshare"
    results: list[ProviderEndpointResult]


class ProviderFetchLogRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    provider_name: str
    endpoint: str
    status: ProviderStatus
    fetch_started_at: datetime
    fetch_finished_at: datetime
    source_time: datetime | None = None
    row_count: int
    error_message: str | None = None
    freshness: str
    confidence: float = Field(ge=0, le=1)
    missing_fields: list[str] = Field(default_factory=list)
    raw_snapshot_id: int | None = None
    normalization_version: str
    created_at: datetime


class ProviderSnapshotSummary(BaseModel):
    id: int
    provider_name: str
    endpoint: str
    market: str
    snapshot_type: str
    source_time: datetime | None = None
    collected_at: datetime
    row_count: int
    normalization_version: str
    raw_summary: dict[str, object]
    preview_rows: list[dict[str, object]] = Field(default_factory=list)


class ProviderEndpointCollectionStatus(BaseModel):
    endpoint: str
    title: str
    latest_status: ProviderStatus | None = None
    latest_quality_status: DataQualityStatus | None = None
    latest_fetch_log_id: int | None = None
    latest_snapshot_id: int | None = None
    latest_checked_at: datetime | None = None
    last_success_at: datetime | None = None
    last_failure_at: datetime | None = None
    row_count: int | None = None
    freshness: str | None = None
    confidence: float | None = Field(default=None, ge=0, le=1)
    missing_fields: list[str] = Field(default_factory=list)
    error_message: str | None = None


class ProviderCollectionStatusResponse(BaseModel):
    provider_name: str
    endpoints: list[ProviderEndpointCollectionStatus]
