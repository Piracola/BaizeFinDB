from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field


class ReportType(StrEnum):
    QUICK = "quick"
    STANDARD = "standard"
    DEEP = "deep"


class CreatableReportType(StrEnum):
    QUICK = "quick"
    STANDARD = "standard"


class PeriodicReportType(StrEnum):
    DAILY = "daily"
    WEEKLY = "weekly"


class ReportStatus(StrEnum):
    GENERATED = "generated"
    NEEDS_HUMAN_REVIEW = "needs_human_review"


class ReportSuggestionLabel(StrEnum):
    FOCUS = "重点关注"
    WATCH = "继续观察"
    CAUTIOUS = "谨慎跟踪"
    IGNORE = "暂不关注"
    RISK_AVOID = "风险回避"


class SignalReportCreate(BaseModel):
    signal_id: int = Field(gt=0)
    report_type: CreatableReportType = CreatableReportType.QUICK


class ReportRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    user_key: str
    signal_id: int | None = None
    report_type: ReportType
    status: ReportStatus
    title: str
    summary: str
    body_markdown: str
    suggestion_label: ReportSuggestionLabel
    review_status: str
    details: dict[str, object]
    created_at: datetime
    updated_at: datetime


class PeriodicReportSubjectRead(BaseModel):
    signal_id: int
    subject_name: str
    priority: str
    lifecycle_stage: str
    review_status: str


class PeriodicReportRead(BaseModel):
    user_key: str
    report_type: PeriodicReportType
    period_start: datetime
    period_end: datetime
    signal_count: int
    report_count: int
    push_count: int
    priority_counts: dict[str, int]
    review_counts: dict[str, int]
    lifecycle_counts: dict[str, int]
    top_subjects: list[PeriodicReportSubjectRead]
    summary: str
    body_markdown: str
