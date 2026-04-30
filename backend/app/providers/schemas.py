from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, Field


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

