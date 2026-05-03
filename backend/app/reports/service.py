from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.report_models import Report
from app.governance.review import review_radar_signal
from app.portfolio.schemas import DEFAULT_USER_KEY
from app.portfolio.service import get_or_create_user
from app.radar.schemas import RadarReviewStatus, RadarSignalDetail
from app.radar.service import get_radar_signal_detail
from app.reports.schemas import (
    CreatableReportType,
    ReportRead,
    ReportStatus,
    ReportSuggestionLabel,
)

REPORT_DISCLAIMER = "说明：仅用于关注、观察、风险和复盘，不构成投资建议。"


class ReportBlockedError(ValueError):
    def __init__(self, reasons: list[str]) -> None:
        super().__init__("report blocked by signal review")
        self.reasons = reasons


async def create_signal_report(
    session: AsyncSession,
    signal_id: int,
    report_type: CreatableReportType,
    user_key: str = DEFAULT_USER_KEY,
) -> ReportRead | None:
    user = await get_or_create_user(session, user_key)
    review = await review_radar_signal(session, signal_id)
    if review is None:
        return None

    if review.review_status == RadarReviewStatus.BLOCKED:
        raise ReportBlockedError(review.reasons)

    signal = await get_radar_signal_detail(session, signal_id)
    if signal is None:
        return None

    status = (
        ReportStatus.NEEDS_HUMAN_REVIEW
        if review.review_status == RadarReviewStatus.NEEDS_HUMAN_REVIEW
        else ReportStatus.GENERATED
    )
    suggestion_label = _suggestion_label(signal, review.review_status)
    title = f"{_report_type_label(report_type)}：{signal.subject_name}"
    summary = _report_summary(signal, suggestion_label)
    body_markdown = _report_body(signal, report_type, suggestion_label, review.reasons)

    report = Report(
        user_id=user.id,
        signal_id=signal.id,
        report_type=report_type.value,
        status=status.value,
        title=title,
        summary=summary,
        body_markdown=body_markdown,
        suggestion_label=suggestion_label.value,
        review_status=review.review_status.value,
        details={
            "source_kind": "radar_signal",
            "source_signal_id": signal.id,
            "source_priority": signal.priority.value,
            "source_lifecycle_stage": signal.lifecycle_stage.value,
            "review_id": review.id,
            "review_reasons": review.reasons,
            "generation_mode": "deterministic_template",
            "model_status": "not_used",
        },
    )
    session.add(report)
    await session.flush()
    await session.commit()
    await session.refresh(report)
    return _report_read(report, user.user_key)


async def list_reports(
    session: AsyncSession,
    user_key: str = DEFAULT_USER_KEY,
    report_type: CreatableReportType | None = None,
    limit: int = 50,
) -> list[ReportRead]:
    user = await get_or_create_user(session, user_key)
    statement = select(Report).where(Report.user_id == user.id)
    if report_type is not None:
        statement = statement.where(Report.report_type == report_type.value)

    statement = statement.order_by(desc(Report.created_at), desc(Report.id)).limit(limit)
    reports = (await session.scalars(statement)).all()
    return [_report_read(report, user.user_key) for report in reports]


async def get_report(
    session: AsyncSession,
    report_id: int,
    user_key: str = DEFAULT_USER_KEY,
) -> ReportRead | None:
    user = await get_or_create_user(session, user_key)
    statement = select(Report).where(Report.id == report_id, Report.user_id == user.id)
    report = await session.scalar(statement)
    return _report_read(report, user.user_key) if report is not None else None


def _report_read(report: Report, user_key: str) -> ReportRead:
    return ReportRead(
        id=report.id,
        user_key=user_key,
        signal_id=report.signal_id,
        report_type=report.report_type,
        status=report.status,
        title=report.title,
        summary=report.summary,
        body_markdown=report.body_markdown,
        suggestion_label=report.suggestion_label,
        review_status=report.review_status,
        details=report.details,
        created_at=report.created_at,
        updated_at=report.updated_at,
    )


def _suggestion_label(
    signal: RadarSignalDetail,
    review_status: RadarReviewStatus,
) -> ReportSuggestionLabel:
    if review_status == RadarReviewStatus.NEEDS_HUMAN_REVIEW:
        return ReportSuggestionLabel.CAUTIOUS

    if signal.priority.value == "P0":
        return ReportSuggestionLabel.FOCUS

    if signal.priority.value == "P1":
        return ReportSuggestionLabel.WATCH

    return ReportSuggestionLabel.CAUTIOUS


def _report_type_label(report_type: CreatableReportType) -> str:
    labels = {
        CreatableReportType.QUICK: "Quick Report",
        CreatableReportType.STANDARD: "Standard Report",
    }
    return labels[report_type]


def _report_summary(
    signal: RadarSignalDetail,
    suggestion_label: ReportSuggestionLabel,
) -> str:
    return (
        f"{signal.subject_name} 当前为 {signal.priority.value} 观察信号，"
        f"生命周期为 {signal.lifecycle_stage.value}，建议标签为{suggestion_label.value}。"
    )


def _report_body(
    signal: RadarSignalDetail,
    report_type: CreatableReportType,
    suggestion_label: ReportSuggestionLabel,
    review_reasons: list[str],
) -> str:
    evidence_lines = [
        f"- {evidence.normalized_summary}（{evidence.evidence_type}，{evidence.freshness}）"
        for evidence in signal.evidences[:5]
    ]
    if not evidence_lines:
        evidence_lines = ["- 暂无可用证据摘要。"]

    return "\n".join(
        [
            f"# {_report_type_label(report_type)}：{signal.subject_name}",
            "",
            "## 结论",
            _report_summary(signal, suggestion_label),
            "",
            "## 后端雷达状态",
            f"- 优先级：{signal.priority.value}",
            f"- 生命周期：{signal.lifecycle_stage.value}",
            f"- 审查状态：{signal.review_status.value}",
            "",
            "## 证据摘要",
            *evidence_lines,
            "",
            "## 风险和观察条件",
            "- 继续观察后续扫描中的优先级、生命周期和证据质量变化。",
            "- 如审查状态需要人工复核，应先人工确认再用于发布或推送。",
            "",
            "## 审查记录",
            f"- 理由：{', '.join(review_reasons) if review_reasons else '无'}",
            "",
            REPORT_DISCLAIMER,
        ],
    )
