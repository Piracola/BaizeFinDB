from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field


class RadarPriority(StrEnum):
    P0 = "P0"
    P1 = "P1"
    P2 = "P2"


class RadarLifecycleStage(StrEnum):
    IGNITION = "ignition"
    DEVELOPING = "developing"
    DIVERGENCE = "divergence"
    RETURNING = "returning"
    CLIMAX = "climax"
    FADING = "fading"
    EXTINGUISHED = "extinguished"


class RadarScanStatus(StrEnum):
    RUNNING = "running"
    SUCCESS = "success"
    NO_DATA = "no_data"
    FAILURE = "failure"


class RadarReviewStatus(StrEnum):
    CANDIDATE = "candidate"


class RadarSignalRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    batch_id: int
    signal_key: str
    subject_type: str
    subject_code: str | None = None
    subject_name: str
    priority: RadarPriority
    lifecycle_stage: RadarLifecycleStage
    review_status: RadarReviewStatus
    title: str
    summary: str
    metrics: dict[str, object]
    evidence_count: int
    created_at: datetime


class SignalEvidenceRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    signal_id: int
    evidence_type: str
    source_name: str
    source_ref: str | None = None
    source_time: datetime | None = None
    collected_at: datetime
    raw_excerpt: str
    normalized_summary: str
    confidence: float = Field(ge=0, le=1)
    freshness: str
    details: dict[str, object]
    public_share_policy: str
    created_at: datetime


class RadarSignalDetail(RadarSignalRead):
    evidences: list[SignalEvidenceRead] = Field(default_factory=list)


class RadarScanRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    status: RadarScanStatus
    started_at: datetime
    finished_at: datetime | None = None
    source_snapshot_ids: list[int]
    summary: dict[str, object]
    error_message: str | None = None
    created_at: datetime
    signals: list[RadarSignalRead] = Field(default_factory=list)
