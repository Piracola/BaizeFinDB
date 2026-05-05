from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.portfolio_models import UserProfile
from app.db.push_models import PushLog
from app.db.radar_models import RadarSignal
from app.db.report_models import Report
from app.governance.review import ReviewContext, review_radar_signal
from app.portfolio.schemas import DEFAULT_USER_KEY
from app.portfolio.service import get_or_create_user
from app.radar.schemas import RadarReviewStatus, RadarSignalDetail
from app.radar.service import get_radar_signal_detail
from app.reports.schemas import (
    CreatableReportType,
    PeriodicReportRead,
    PeriodicReportSubjectRead,
    PeriodicReportType,
    ReportRead,
    ReportStatus,
    ReportSuggestionLabel,
    ReportType,
)

REPORT_DISCLAIMER = "说明：仅用于关注、观察、风险和复盘，不构成投资建议。"
REPORT_TIMEZONE = ZoneInfo("Asia/Shanghai")
PERIODIC_SUBJECT_LIMIT = 10


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
    return await _create_signal_report_for_user(
        session=session,
        user=user,
        signal_id=signal_id,
        report_type=ReportType(report_type.value),
        commit=True,
    )


async def create_manual_deep_signal_report(
    session: AsyncSession,
    signal_id: int,
    user_key: str = DEFAULT_USER_KEY,
) -> ReportRead | None:
    user = await get_or_create_user(session, user_key)
    return await _create_signal_report_for_user(
        session=session,
        user=user,
        signal_id=signal_id,
        report_type=ReportType.DEEP,
        details_update={
            "manual_confirmation": True,
            "confirmed_action": "manual_deep_report",
        },
        commit=True,
    )


async def ensure_signal_report(
    session: AsyncSession,
    signal_id: int,
    report_type: CreatableReportType,
    user_key: str = DEFAULT_USER_KEY,
    details_update: dict[str, object] | None = None,
    commit: bool = True,
) -> ReportRead | None:
    user = await get_or_create_user(session, user_key)
    existing_report = await _find_existing_signal_report(
        session=session,
        user_id=user.id,
        signal_id=signal_id,
        report_type=ReportType(report_type.value),
    )
    if existing_report is not None:
        return _report_read(existing_report, user.user_key)

    return await _create_signal_report_for_user(
        session=session,
        user=user,
        signal_id=signal_id,
        report_type=ReportType(report_type.value),
        details_update=details_update,
        commit=commit,
    )


async def _create_signal_report_for_user(
    session: AsyncSession,
    user: UserProfile,
    signal_id: int,
    report_type: ReportType,
    details_update: dict[str, object] | None = None,
    commit: bool = True,
) -> ReportRead | None:
    review = await review_radar_signal(
        session,
        signal_id,
        review_context=ReviewContext.REPORT_PUBLICATION,
    )
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
    details = {
        "source_kind": "radar_signal",
        "source_signal_id": signal.id,
        "source_priority": signal.priority.value,
        "source_lifecycle_stage": signal.lifecycle_stage.value,
        "review_id": review.id,
        "review_reasons": review.reasons,
        "generation_mode": "deterministic_template",
        "model_status": "not_used",
        "report_depth": report_type.value,
    }
    if details_update:
        details.update(details_update)

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
        details=details,
    )
    session.add(report)
    await session.flush()
    if commit:
        await session.commit()

    await session.refresh(report)
    return _report_read(report, user.user_key)


async def list_reports(
    session: AsyncSession,
    user_key: str = DEFAULT_USER_KEY,
    report_type: ReportType | None = None,
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


async def generate_periodic_report(
    session: AsyncSession,
    report_type: PeriodicReportType,
    user_key: str = DEFAULT_USER_KEY,
    now: datetime | None = None,
) -> PeriodicReportRead:
    user = await get_or_create_user(session, user_key)
    period_start, period_end = _period_bounds(report_type, now or datetime.now(UTC))

    signal_statement = (
        select(RadarSignal)
        .where(
            RadarSignal.created_at >= period_start,
            RadarSignal.created_at < period_end,
        )
        .order_by(desc(RadarSignal.created_at), desc(RadarSignal.id))
    )
    signals = list((await session.scalars(signal_statement)).all())

    report_statement = select(Report).where(
        Report.user_id == user.id,
        Report.created_at >= period_start,
        Report.created_at < period_end,
    )
    user_reports = list((await session.scalars(report_statement)).all())

    push_statement = select(PushLog).where(
        PushLog.user_id == user.id,
        PushLog.channel == "telegram",
        PushLog.created_at >= period_start,
        PushLog.created_at < period_end,
    )
    push_logs = list((await session.scalars(push_statement)).all())

    priority_counts = _field_counts(signals, "priority", ("P0", "P1", "P2"))
    review_counts = _field_counts(
        signals,
        "review_status",
        ("candidate", "approved", "blocked", "needs_human_review"),
    )
    lifecycle_counts = _field_counts(
        signals,
        "lifecycle_stage",
        ("ignition", "developing", "divergence", "returning", "climax", "fading", "extinguished"),
    )
    top_subjects = _periodic_top_subjects(signals)
    summary = _periodic_summary(
        report_type=report_type,
        signal_count=len(signals),
        report_count=len(user_reports),
        push_count=len(push_logs),
        priority_counts=priority_counts,
    )
    body_markdown = _periodic_body(
        report_type=report_type,
        period_start=period_start,
        period_end=period_end,
        priority_counts=priority_counts,
        review_counts=review_counts,
        lifecycle_counts=lifecycle_counts,
        top_subjects=top_subjects,
        report_count=len(user_reports),
        push_count=len(push_logs),
    )

    return PeriodicReportRead(
        user_key=user.user_key,
        report_type=report_type,
        period_start=period_start,
        period_end=period_end,
        signal_count=len(signals),
        report_count=len(user_reports),
        push_count=len(push_logs),
        priority_counts=priority_counts,
        review_counts=review_counts,
        lifecycle_counts=lifecycle_counts,
        top_subjects=top_subjects,
        summary=summary,
        body_markdown=body_markdown,
    )


async def _find_existing_signal_report(
    session: AsyncSession,
    user_id: int,
    signal_id: int,
    report_type: ReportType,
) -> Report | None:
    statement = (
        select(Report)
        .where(
            Report.user_id == user_id,
            Report.signal_id == signal_id,
            Report.report_type == report_type.value,
        )
        .order_by(desc(Report.created_at), desc(Report.id))
        .limit(1)
    )
    return await session.scalar(statement)


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


def _period_bounds(
    report_type: PeriodicReportType,
    now: datetime,
) -> tuple[datetime, datetime]:
    if now.tzinfo is None:
        now = now.replace(tzinfo=UTC)

    local_now = now.astimezone(REPORT_TIMEZONE)
    if report_type == PeriodicReportType.DAILY:
        local_start = local_now.replace(hour=0, minute=0, second=0, microsecond=0)
    else:
        local_day_start = local_now.replace(hour=0, minute=0, second=0, microsecond=0)
        local_start = local_day_start - timedelta(days=local_day_start.weekday())

    return local_start.astimezone(UTC), local_now.astimezone(UTC)


def _field_counts(
    rows: list[RadarSignal],
    field_name: str,
    known_values: tuple[str, ...],
) -> dict[str, int]:
    counts = {value: 0 for value in known_values}
    for row in rows:
        value = str(getattr(row, field_name))
        counts[value] = counts.get(value, 0) + 1
    return counts


def _periodic_top_subjects(signals: list[RadarSignal]) -> list[PeriodicReportSubjectRead]:
    priority_rank = {"P0": 0, "P1": 1, "P2": 2}
    sorted_signals = sorted(
        signals,
        key=lambda signal: (
            priority_rank.get(signal.priority, 99),
            -signal.created_at.timestamp(),
            -signal.id,
        ),
    )

    return [
        PeriodicReportSubjectRead(
            signal_id=signal.id,
            subject_name=signal.subject_name,
            priority=signal.priority,
            lifecycle_stage=signal.lifecycle_stage,
            review_status=signal.review_status,
        )
        for signal in sorted_signals[:PERIODIC_SUBJECT_LIMIT]
    ]


def _periodic_summary(
    report_type: PeriodicReportType,
    signal_count: int,
    report_count: int,
    push_count: int,
    priority_counts: dict[str, int],
) -> str:
    label = "日报" if report_type == PeriodicReportType.DAILY else "周报"
    return (
        f"{label}汇总：本周期记录 {signal_count} 条雷达信号，"
        f"P0/P1/P2 为 {priority_counts.get('P0', 0)}/"
        f"{priority_counts.get('P1', 0)}/{priority_counts.get('P2', 0)}，"
        f"生成 {report_count} 份报告，记录 {push_count} 次 Telegram 推送。"
    )


def _periodic_body(
    report_type: PeriodicReportType,
    period_start: datetime,
    period_end: datetime,
    priority_counts: dict[str, int],
    review_counts: dict[str, int],
    lifecycle_counts: dict[str, int],
    top_subjects: list[PeriodicReportSubjectRead],
    report_count: int,
    push_count: int,
) -> str:
    title = "日报" if report_type == PeriodicReportType.DAILY else "周报"
    subject_lines = [
        (
            f"- #{subject.signal_id} [{subject.priority}] {subject.subject_name} | "
            f"生命周期：{subject.lifecycle_stage} | 审查：{subject.review_status}"
        )
        for subject in top_subjects
    ] or ["- 暂无雷达信号。"]

    return "\n".join(
        [
            f"# BaizeFinDB {title}",
            "",
            f"- 周期开始：{period_start.isoformat()}",
            f"- 周期结束：{period_end.isoformat()}",
            (
                "- 优先级："
                f"P0 {priority_counts.get('P0', 0)} / "
                f"P1 {priority_counts.get('P1', 0)} / "
                f"P2 {priority_counts.get('P2', 0)}"
            ),
            (
                "- 审查："
                f"approved {review_counts.get('approved', 0)} / "
                f"blocked {review_counts.get('blocked', 0)} / "
                f"needs_human_review {review_counts.get('needs_human_review', 0)}"
            ),
            f"- 报告：{report_count} 份",
            f"- Telegram 推送：{push_count} 次",
            "",
            "## 生命周期分布",
            *[f"- {stage}: {count}" for stage, count in lifecycle_counts.items() if count],
            "",
            "## 重点主题",
            *subject_lines,
            "",
            REPORT_DISCLAIMER,
        ],
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


def _report_type_label(report_type: ReportType) -> str:
    labels = {
        ReportType.QUICK: "Quick Report",
        ReportType.STANDARD: "Standard Report",
        ReportType.DEEP: "Deep Report",
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
    report_type: ReportType,
    suggestion_label: ReportSuggestionLabel,
    review_reasons: list[str],
) -> str:
    if report_type == ReportType.DEEP:
        return _deep_report_body(signal, suggestion_label, review_reasons)

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


def _deep_report_body(
    signal: RadarSignalDetail,
    suggestion_label: ReportSuggestionLabel,
    review_reasons: list[str],
) -> str:
    evidence_lines = [
        (
            f"- 证据 {index}: {evidence.normalized_summary}"
            f"（类型：{evidence.evidence_type}；时效：{evidence.freshness}）"
        )
        for index, evidence in enumerate(signal.evidences[:10], start=1)
    ] or ["- 暂无可用证据摘要。"]
    metric_lines = [
        f"- {key}: {value}"
        for key, value in sorted(signal.metrics.items())
        if value is not None and not isinstance(value, (dict, list))
    ][:8] or ["- 暂无可展示指标。"]
    review_reason_text = ", ".join(review_reasons) if review_reasons else "无"

    return "\n".join(
        [
            f"# Deep Report：{signal.subject_name}",
            "",
            "## 核心结论",
            _report_summary(signal, suggestion_label),
            "",
            "## 雷达状态",
            f"- 优先级：{signal.priority.value}",
            f"- 生命周期：{signal.lifecycle_stage.value}",
            f"- 审查状态：{signal.review_status.value}",
            f"- 建议标签：{suggestion_label.value}",
            "",
            "## 指标观察",
            *metric_lines,
            "",
            "## 证据地图",
            *evidence_lines,
            "",
            "## 分歧和风险复核",
            f"- 审查理由：{review_reason_text}",
            "- 如果证据质量、来源时效或审查状态变化，需要重新生成或人工复核。",
            "",
            "## 后续观察条件",
            "- 继续观察后续扫描中的优先级、生命周期、证据数量和数据质量变化。",
            "- 关注同一主题是否出现连续触发、风险事件扩散或证据失效。",
            "- 需要人工复核时，应先完成内部确认，再用于发布、分享或导出。",
            "",
            "## 审计边界",
            (
                "- 本报告由确定性模板生成，未调用模型、外部接口、Provider、扫描、"
                "推送或 evidence 写入。"
            ),
            "- 本报告只使用已有雷达信号、证据摘要和治理审查结果。",
            "",
            REPORT_DISCLAIMER,
        ],
    )
