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
    APPROVED = "approved"
    BLOCKED = "blocked"
    NEEDS_HUMAN_REVIEW = "needs_human_review"


class RadarSignalShareStatus(StrEnum):
    READY = "ready"
    BLOCKED = "blocked"


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


class RadarSignalReviewRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    signal_id: int
    review_status: RadarReviewStatus
    reviewer: str
    rule_version: str
    reasons: list[str]
    details: dict[str, object]
    created_at: datetime


class RadarSignalShareEvidenceRead(BaseModel):
    summary: str
    evidence_label: str
    confidence_label: str
    freshness_label: str


class RadarSignalPublicShareRead(BaseModel):
    title: str
    summary: str
    subject_name: str
    priority_label: str
    lifecycle_label: str
    evidences: list[RadarSignalShareEvidenceRead] = Field(default_factory=list)
    disclaimer: str


class RadarSignalSharePreviewRead(BaseModel):
    signal_id: int
    share_status: RadarSignalShareStatus
    review_status: RadarReviewStatus
    latest_review_id: int | None = None
    blocked_reasons: list[str]
    sanitization_notes: list[str]
    title: str
    summary: str
    subject_type: str
    subject_code: str | None = None
    subject_name: str
    priority: RadarPriority
    lifecycle_stage: RadarLifecycleStage
    evidences: list[RadarSignalShareEvidenceRead] = Field(default_factory=list)
    disclaimer: str
    public_payload: RadarSignalPublicShareRead


class RadarSubjectOverviewRead(BaseModel):
    signal_key: str
    subject_type: str
    subject_code: str | None = None
    subject_name: str
    latest_signal: RadarSignalRead


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


class RadarOverviewRead(BaseModel):
    latest_scan: RadarScanRead | None = None
    active_signals: list[RadarSignalRead] = Field(default_factory=list)
    current_subjects: list[RadarSubjectOverviewRead] = Field(default_factory=list)
    priority_counts: dict[str, int]
    subject_count: int
