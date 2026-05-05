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


class RadarSignalMetricHighlightRead(BaseModel):
    label: str
    value: str
    interpretation: str


class RadarSignalEvidenceSummaryRead(BaseModel):
    evidence_count: int
    evidence_types: list[str] = Field(default_factory=list, max_length=6)
    summaries: list[str] = Field(default_factory=list, max_length=3)
    freshness_labels: list[str] = Field(default_factory=list, max_length=3)
    confidence_labels: list[str] = Field(default_factory=list, max_length=3)


class RadarSignalReviewSummaryRead(BaseModel):
    status: RadarReviewStatus
    latest_review_id: int | None = None
    reasons: list[str] = Field(default_factory=list, max_length=8)
    human_review_required: bool


class RadarSignalAgentInputsRead(BaseModel):
    signal_context: list[str] = Field(default_factory=list, max_length=6)
    evidence_summaries: list[str] = Field(default_factory=list, max_length=3)
    guardrails: list[str] = Field(default_factory=list, max_length=6)


class RadarSignalAgentAssessmentStatus(StrEnum):
    OK = "ok"
    WARNING = "warning"
    BLOCKED = "blocked"
    NOT_APPLICABLE = "not_applicable"


class RadarSignalAgentAssessmentRead(BaseModel):
    agent_id: str
    label: str
    status: RadarSignalAgentAssessmentStatus
    summary: str
    findings: list[str] = Field(default_factory=list, max_length=5)
    next_actions: list[str] = Field(default_factory=list, max_length=5)


class RadarSignalAnalysisRead(BaseModel):
    signal_id: int
    subject_type: str
    subject_code: str | None = None
    subject_name: str
    priority: RadarPriority
    lifecycle_stage: RadarLifecycleStage
    review_status: RadarReviewStatus
    analysis_title: str
    key_points: list[str] = Field(default_factory=list, max_length=5)
    metric_highlights: list[RadarSignalMetricHighlightRead] = Field(
        default_factory=list,
        max_length=6,
    )
    risk_flags: list[str] = Field(default_factory=list, max_length=8)
    evidence_summary: RadarSignalEvidenceSummaryRead
    review_summary: RadarSignalReviewSummaryRead
    agent_inputs: RadarSignalAgentInputsRead
    agent_assessments: list[RadarSignalAgentAssessmentRead] = Field(
        default_factory=list,
        max_length=5,
    )
    next_actions: list[str] = Field(default_factory=list, max_length=5)


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


class RadarStockBacktraceEvidenceRead(BaseModel):
    signal_id: int
    subject_type: str
    subject_code: str | None = None
    subject_name: str
    priority: RadarPriority
    lifecycle_stage: RadarLifecycleStage
    stock_name: str
    stock_pct_change: float
    evidence_label: str
    source_snapshot_id: int | None = None


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
    stock_backtrace_evidences: list[RadarStockBacktraceEvidenceRead] = Field(default_factory=list)
    priority_counts: dict[str, int]
    lifecycle_counts: dict[str, int]
    subject_count: int
