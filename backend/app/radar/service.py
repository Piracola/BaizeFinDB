from contextlib import suppress
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy import desc, or_, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.db.provider_models import DataQualityCheck, MarketSnapshot
from app.db.radar_models import RadarScanBatch, RadarSignal, RadarSignalReview, SignalEvidence
from app.governance.sanitization import redact_source_locators, truncate_text
from app.radar.rules import (
    RadarRuleResult,
    classify_risk_event,
    classify_sector_movement,
)
from app.radar.schemas import (
    RadarLifecycleStage,
    RadarOverviewRead,
    RadarPriority,
    RadarReviewStatus,
    RadarScanRead,
    RadarScanStatus,
    RadarSignalAgentAssessmentRead,
    RadarSignalAgentAssessmentStatus,
    RadarSignalAgentInputsRead,
    RadarSignalAnalysisRead,
    RadarSignalDetail,
    RadarSignalEvidenceSummaryRead,
    RadarSignalMetricHighlightRead,
    RadarSignalRead,
    RadarSignalReviewSummaryRead,
    RadarStockBacktraceEvidenceRead,
    RadarSubjectOverviewRead,
    SignalEvidenceRead,
)

MARKET_MAINLINE_SOURCE_ENDPOINTS = (
    "stock_board_industry_name_em",
    "stock_board_concept_name_em",
)
RISK_EVENT_SOURCE_ENDPOINTS = (
    "risk_events",
    "announcement_events",
    "regulatory_events",
    "black_swan_events",
)
TUSHARE_ANNOUNCEMENT_SOURCE_ENDPOINTS = ("anns_d",)
SENTIMENT_SOURCE_ENDPOINTS = (
    "stock_zt_pool_em",
    "stock_zt_pool_dtgc_em",
    "stock_zt_pool_zbgc_em",
)
RADAR_SOURCE_ENDPOINTS = (
    MARKET_MAINLINE_SOURCE_ENDPOINTS
    + RISK_EVENT_SOURCE_ENDPOINTS
    + TUSHARE_ANNOUNCEMENT_SOURCE_ENDPOINTS
    + SENTIMENT_SOURCE_ENDPOINTS
)
RADAR_SOURCE_PROVIDER_NAMES = ("akshare", "manual")
MAX_SIGNALS_PER_SCAN = 20
P2_OBSERVATION_WINDOW_DAYS = 7
MAX_ERROR_MESSAGE_LENGTH = 300
MAX_ANALYSIS_TEXT_LENGTH = 180
MAX_ANALYSIS_KEY_POINTS = 5
MAX_ANALYSIS_METRIC_HIGHLIGHTS = 6
MAX_ANALYSIS_RISK_FLAGS = 8
MAX_ANALYSIS_EVIDENCE_SUMMARIES = 3
MAX_ANALYSIS_AGENT_ASSESSMENTS = 5
MAX_ANALYSIS_AGENT_FINDINGS = 5
MAJOR_RISK_ANNOUNCEMENT_KEYWORDS = (
    "立案调查",
    "行政处罚事先告知",
    "重大违法",
    "退市风险",
    "终止上市",
    "暂停上市",
    "强制退市",
    "无法表示意见",
    "被实施退市风险警示",
    "重大诉讼",
    "债务逾期",
    "资金占用",
    "违规担保",
)
CRITICAL_RISK_ANNOUNCEMENT_KEYWORDS = (
    "终止上市",
    "强制退市",
    "重大违法",
    "无法表示意见",
)


@dataclass(frozen=True)
class SignalCandidate:
    snapshot: MarketSnapshot
    row: dict[str, object]
    subject_type: str
    subject_code: str | None
    subject_name: str
    metrics: dict[str, object]
    data_quality: dict[str, object]
    rule_result: RadarRuleResult


@dataclass(frozen=True)
class CandidateContinuity:
    previous_signal_id: int | None
    previous_priority: str | None
    previous_lifecycle_stage: str | None
    previous_pct_change: float | None
    previous_breadth: float | None
    pct_change_delta: float | None
    breadth_delta: float | None
    consecutive_p1_count: int
    quick_report_candidate: bool
    adjusted_lifecycle_stage: RadarLifecycleStage
    lifecycle_transition: str
    continuity_reasons: list[str]


async def run_radar_scan(session: AsyncSession) -> RadarScanRead:
    started_at = datetime.now(UTC)
    batch = RadarScanBatch(
        status=RadarScanStatus.RUNNING.value,
        started_at=started_at,
        source_snapshot_ids=[],
        summary={},
    )
    session.add(batch)
    await session.flush()
    batch_id = batch.id
    await session.commit()

    snapshots: list[MarketSnapshot] = []
    source_snapshot_ids: list[int] = []
    source_endpoints: list[str] = []
    snapshot_quality_summaries: dict[int, dict[str, object]] = {}
    market_sentiment: dict[str, object] = _empty_market_sentiment_summary()
    candidates: list[SignalCandidate] = []
    continuities: list[CandidateContinuity] = []

    try:
        snapshots = await _load_latest_source_snapshots(session)
        source_snapshot_ids = [snapshot.id for snapshot in snapshots]
        source_endpoints = [snapshot.endpoint for snapshot in snapshots]
        snapshot_quality_summaries = await _load_snapshot_quality_summaries(
            session,
            snapshots,
        )
        market_sentiment = _market_sentiment_summary(snapshots)
        candidates = _build_signal_candidates(
            snapshots,
            snapshot_quality_summaries,
            market_sentiment=market_sentiment,
        )

        for candidate in candidates:
            continuity = await _candidate_continuity(session, candidate, started_at)
            continuities.append(continuity)

            signal = _new_signal(batch_id, candidate, continuity)
            session.add(signal)
            await session.flush()

            session.add(_new_evidence(signal.id, candidate, continuity))
            signal.evidence_count = 1

        batch.status = (
            RadarScanStatus.SUCCESS.value if candidates else RadarScanStatus.NO_DATA.value
        )
        batch.finished_at = datetime.now(UTC)
        batch.source_snapshot_ids = source_snapshot_ids
        batch.error_message = None
        batch.summary = _scan_success_summary(
            source_endpoints,
            len(source_snapshot_ids),
            snapshot_quality_summaries,
            candidates,
            continuities,
            market_sentiment,
        )

        await session.commit()
    except SQLAlchemyError as exc:
        await _best_effort_record_scan_failure(
            session=session,
            batch_id=batch_id,
            source_snapshot_ids=source_snapshot_ids,
            source_endpoints=source_endpoints,
            snapshot_quality_summaries=snapshot_quality_summaries,
            candidates=candidates,
            continuities=continuities,
            exc=exc,
        )
        raise
    except Exception as exc:
        await _record_scan_failure(
            session=session,
            batch_id=batch_id,
            source_snapshot_ids=source_snapshot_ids,
            source_endpoints=source_endpoints,
            snapshot_quality_summaries=snapshot_quality_summaries,
            candidates=candidates,
            continuities=continuities,
            exc=exc,
        )

    scan = await get_radar_scan(session, batch_id)
    if scan is None:
        raise RuntimeError("radar scan was committed but could not be reloaded")

    return scan


async def get_latest_radar_scan(session: AsyncSession) -> RadarScanRead | None:
    statement = (
        select(RadarScanBatch)
        .order_by(desc(RadarScanBatch.started_at), desc(RadarScanBatch.id))
        .limit(1)
    )
    batch = await session.scalar(statement)
    return await _scan_read(session, batch) if batch is not None else None


async def get_radar_scan(session: AsyncSession, scan_id: int) -> RadarScanRead | None:
    batch = await session.get(RadarScanBatch, scan_id)
    return await _scan_read(session, batch) if batch is not None else None


async def get_radar_overview(
    session: AsyncSession,
    limit: int = 50,
    as_of: datetime | None = None,
) -> RadarOverviewRead:
    latest_scan = await get_latest_radar_scan(session)
    visible_signals = _filter_visible_signals(
        latest_scan.signals if latest_scan else [],
        as_of=as_of,
    )
    if latest_scan is not None:
        latest_scan = latest_scan.model_copy(update={"signals": visible_signals})

    current_signals = _dedupe_subject_signals(visible_signals)
    active_signals = current_signals[:limit]

    return RadarOverviewRead(
        latest_scan=latest_scan,
        active_signals=active_signals,
        current_subjects=[
            RadarSubjectOverviewRead(
                signal_key=signal.signal_key,
                subject_type=signal.subject_type,
                subject_code=signal.subject_code,
                subject_name=signal.subject_name,
                latest_signal=signal,
            )
            for signal in active_signals
        ],
        stock_backtrace_evidences=_stock_backtrace_evidences(current_signals)[:limit],
        priority_counts=_signal_priority_counts(current_signals),
        lifecycle_counts=_signal_lifecycle_counts(current_signals),
        subject_count=len(current_signals),
    )


async def list_radar_signals(
    session: AsyncSession,
    priority: RadarPriority | None = None,
    limit: int = 50,
    include_expired_p2: bool = False,
    as_of: datetime | None = None,
) -> list[RadarSignalRead]:
    statement = select(RadarSignal)

    if priority is not None:
        statement = statement.where(RadarSignal.priority == priority.value)

    if not include_expired_p2:
        statement = statement.where(
            or_(
                RadarSignal.priority != RadarPriority.P2.value,
                RadarSignal.created_at >= _p2_observation_cutoff(as_of),
            )
        )

    statement = statement.order_by(
        desc(RadarSignal.created_at),
        desc(RadarSignal.id),
    ).limit(limit)
    signals = (await session.scalars(statement)).all()
    return [RadarSignalRead.model_validate(signal) for signal in signals]


async def get_radar_signal_detail(
    session: AsyncSession,
    signal_id: int,
) -> RadarSignalDetail | None:
    signal = await session.get(RadarSignal, signal_id)
    if signal is None:
        return None

    evidence_statement = (
        select(SignalEvidence)
        .where(SignalEvidence.signal_id == signal_id)
        .order_by(desc(SignalEvidence.created_at), desc(SignalEvidence.id))
    )
    evidences = (await session.scalars(evidence_statement)).all()
    signal_data = RadarSignalRead.model_validate(signal).model_dump()
    return RadarSignalDetail(
        **signal_data,
        evidences=[SignalEvidenceRead.model_validate(evidence) for evidence in evidences],
    )


async def get_radar_signal_analysis(
    session: AsyncSession,
    signal_id: int,
) -> RadarSignalAnalysisRead | None:
    signal = await session.get(RadarSignal, signal_id)
    if signal is None:
        return None

    evidence_statement = (
        select(SignalEvidence)
        .where(SignalEvidence.signal_id == signal_id)
        .order_by(desc(SignalEvidence.created_at), desc(SignalEvidence.id))
    )
    evidences = list((await session.scalars(evidence_statement)).all())
    latest_review = await _latest_signal_review(session, signal_id)

    return _build_signal_analysis(signal, evidences, latest_review)


async def _latest_signal_review(
    session: AsyncSession,
    signal_id: int,
) -> RadarSignalReview | None:
    statement = (
        select(RadarSignalReview)
        .where(RadarSignalReview.signal_id == signal_id)
        .order_by(desc(RadarSignalReview.created_at), desc(RadarSignalReview.id))
        .limit(1)
    )
    return await session.scalar(statement)


def _build_signal_analysis(
    signal: RadarSignal,
    evidences: list[SignalEvidence],
    latest_review: RadarSignalReview | None,
) -> RadarSignalAnalysisRead:
    evidence_summary = _analysis_evidence_summary(evidences)
    review_summary = _analysis_review_summary(signal, latest_review)
    key_points = _analysis_key_points(signal, evidence_summary, review_summary)
    metric_highlights = _analysis_metric_highlights(signal)
    risk_flags = _analysis_risk_flags(signal, evidences, latest_review)
    next_actions = _analysis_next_actions(signal, review_summary)

    return RadarSignalAnalysisRead(
        signal_id=signal.id,
        subject_type=signal.subject_type,
        subject_code=signal.subject_code,
        subject_name=_analysis_text(signal.subject_name),
        priority=signal.priority,
        lifecycle_stage=signal.lifecycle_stage,
        review_status=signal.review_status,
        analysis_title=_analysis_title(signal),
        key_points=key_points,
        metric_highlights=metric_highlights,
        risk_flags=risk_flags,
        evidence_summary=evidence_summary,
        review_summary=review_summary,
        agent_inputs=_analysis_agent_inputs(signal, evidence_summary, key_points),
        agent_assessments=_analysis_agent_assessments(
            signal,
            evidence_summary,
            review_summary,
            metric_highlights,
            risk_flags,
            next_actions,
        ),
        next_actions=next_actions,
    )


def _analysis_title(signal: RadarSignal) -> str:
    return _analysis_text(f"{signal.priority} research brief: {signal.subject_name}")


def _analysis_key_points(
    signal: RadarSignal,
    evidence_summary: RadarSignalEvidenceSummaryRead,
    review_summary: RadarSignalReviewSummaryRead,
) -> list[str]:
    points = [
        (
            f"{_analysis_text(signal.subject_name)} is a {signal.priority} "
            f"research-attention signal in {signal.lifecycle_stage} stage."
        ),
        _analysis_text(signal.summary),
        (
            f"Backend rule priority and lifecycle remain unchanged: "
            f"{signal.priority} / {signal.lifecycle_stage}."
        ),
        (
            f"Review status is {review_summary.status}; "
            f"{evidence_summary.evidence_count} evidence item(s) are summarized."
        ),
    ]
    if review_summary.human_review_required:
        points.append("Human review is required before report, push, or public sharing.")

    return _bounded_unique(points, MAX_ANALYSIS_KEY_POINTS)


def _analysis_metric_highlights(signal: RadarSignal) -> list[RadarSignalMetricHighlightRead]:
    metrics = signal.metrics
    highlights: list[RadarSignalMetricHighlightRead] = []

    if "pct_change" in metrics:
        highlights.append(
            RadarSignalMetricHighlightRead(
                label="movement",
                value=f"{_float(metrics.get('pct_change')):g}%",
                interpretation="Subject movement strength from provider snapshot.",
            )
        )

    if "breadth" in metrics:
        breadth = _float(metrics.get("breadth"))
        highlights.append(
            RadarSignalMetricHighlightRead(
                label="breadth",
                value=f"{breadth * 100:.1f}%",
                interpretation="Share of rising constituents in the snapshot.",
            )
        )

    if "rising_count" in metrics or "falling_count" in metrics:
        rising_count = _int(metrics.get("rising_count"))
        falling_count = _int(metrics.get("falling_count"))
        highlights.append(
            RadarSignalMetricHighlightRead(
                label="constituent_balance",
                value=f"{rising_count} rising / {falling_count} falling",
                interpretation="Breadth context; not a standalone rule override.",
            )
        )

    leading_stock = _optional_text(metrics.get("leading_stock"))
    if leading_stock is not None:
        pct = _float(metrics.get("leading_stock_pct_change"))
        value = (
            _analysis_text(f"{leading_stock} +{pct:g}%")
            if pct
            else _analysis_text(leading_stock)
        )
        highlights.append(
            RadarSignalMetricHighlightRead(
                label="leading_stock_context",
                value=value,
                interpretation="Single-stock move is supporting context, not the priority source.",
            )
        )

    continuity = metrics.get("continuity")
    if isinstance(continuity, dict) and continuity.get("quick_report_candidate") is True:
        highlights.append(
            RadarSignalMetricHighlightRead(
                label="continuity",
                value="quick-report candidate",
                interpretation="Repeated P1 behavior needs review before any publishing flow.",
            )
        )

    risk_event_type = _optional_text(metrics.get("risk_event_type"))
    severity = _optional_text(metrics.get("severity"))
    if risk_event_type or severity:
        risk_context = " / ".join(part for part in (risk_event_type, severity) if part)
        highlights.append(
            RadarSignalMetricHighlightRead(
                label="risk_context",
                value=_analysis_text(risk_context),
                interpretation=(
                    "Risk-event context is treated separately from market mainline signals."
                ),
            )
        )

    return highlights[:MAX_ANALYSIS_METRIC_HIGHLIGHTS]


def _analysis_risk_flags(
    signal: RadarSignal,
    evidences: list[SignalEvidence],
    latest_review: RadarSignalReview | None,
) -> list[str]:
    flags: list[str] = []

    if not evidences or signal.evidence_count == 0:
        flags.append("missing_evidence")

    if signal.review_status == RadarReviewStatus.BLOCKED.value:
        flags.append("review_blocked")
    elif signal.review_status == RadarReviewStatus.NEEDS_HUMAN_REVIEW.value:
        flags.append("review_needs_human_review")

    provider_quality = signal.metrics.get("provider_quality")
    if isinstance(provider_quality, dict):
        status = _optional_text(provider_quality.get("status"))
        if status and status != "ok":
            flags.append(f"provider_quality_{status}")

    if _optional_text(signal.metrics.get("risk_event_type")):
        flags.append("risk_event_candidate")

    for evidence in evidences:
        freshness = evidence.freshness.strip().lower()
        if any(marker in freshness for marker in ("stale", "expired", "outdated", "too_old")):
            flags.append("stale_evidence")

    if latest_review is not None:
        flags.extend(str(reason) for reason in latest_review.reasons)

    return _bounded_unique(flags, MAX_ANALYSIS_RISK_FLAGS)


def _analysis_evidence_summary(
    evidences: list[SignalEvidence],
) -> RadarSignalEvidenceSummaryRead:
    return RadarSignalEvidenceSummaryRead(
        evidence_count=len(evidences),
        evidence_types=_bounded_unique(
            [_evidence_type_label(evidence.evidence_type) for evidence in evidences],
            6,
        ),
        summaries=[
            _analysis_text(evidence.normalized_summary)
            for evidence in evidences[:MAX_ANALYSIS_EVIDENCE_SUMMARIES]
        ],
        freshness_labels=_bounded_unique(
            [_freshness_label(evidence.freshness) for evidence in evidences],
            MAX_ANALYSIS_EVIDENCE_SUMMARIES,
        ),
        confidence_labels=_bounded_unique(
            [_confidence_label(evidence.confidence) for evidence in evidences],
            MAX_ANALYSIS_EVIDENCE_SUMMARIES,
        ),
    )


def _analysis_review_summary(
    signal: RadarSignal,
    latest_review: RadarSignalReview | None,
) -> RadarSignalReviewSummaryRead:
    status = (
        RadarReviewStatus(latest_review.review_status)
        if latest_review is not None
        else RadarReviewStatus(signal.review_status)
    )
    reasons = [str(reason) for reason in latest_review.reasons] if latest_review is not None else []
    return RadarSignalReviewSummaryRead(
        status=status,
        latest_review_id=latest_review.id if latest_review is not None else None,
        reasons=_bounded_unique(reasons, 8),
        human_review_required=status
        in {
            RadarReviewStatus.BLOCKED,
            RadarReviewStatus.NEEDS_HUMAN_REVIEW,
            RadarReviewStatus.CANDIDATE,
        },
    )


def _analysis_agent_inputs(
    signal: RadarSignal,
    evidence_summary: RadarSignalEvidenceSummaryRead,
    key_points: list[str],
) -> RadarSignalAgentInputsRead:
    return RadarSignalAgentInputsRead(
        signal_context=[
            _analysis_text(signal.title),
            f"priority={signal.priority}",
            f"lifecycle_stage={signal.lifecycle_stage}",
            f"review_status={signal.review_status}",
        ],
        evidence_summaries=evidence_summary.summaries,
        guardrails=[
            "Use these fields for research explanation only.",
            "Do not override backend rule priority, lifecycle, or review status.",
            "Do not produce trading instructions.",
            "Do not request or reveal raw source locators.",
            "Treat key points as bounded context, not a full evidence archive.",
        ],
    )


def _analysis_agent_assessments(
    signal: RadarSignal,
    evidence_summary: RadarSignalEvidenceSummaryRead,
    review_summary: RadarSignalReviewSummaryRead,
    metric_highlights: list[RadarSignalMetricHighlightRead],
    risk_flags: list[str],
    next_actions: list[str],
) -> list[RadarSignalAgentAssessmentRead]:
    assessments = [
        _data_quality_agent_assessment(evidence_summary, risk_flags),
        _risk_agent_assessment(review_summary, risk_flags),
        _momentum_agent_assessment(signal, metric_highlights),
        _evidence_agent_assessment(evidence_summary),
        _report_agent_assessment(review_summary, next_actions),
    ]
    return assessments[:MAX_ANALYSIS_AGENT_ASSESSMENTS]


def _data_quality_agent_assessment(
    evidence_summary: RadarSignalEvidenceSummaryRead,
    risk_flags: list[str],
) -> RadarSignalAgentAssessmentRead:
    quality_flags = [
        flag
        for flag in risk_flags
        if flag == "missing_evidence"
        or flag == "stale_evidence"
        or flag.startswith("provider_quality_")
    ]
    status = (
        RadarSignalAgentAssessmentStatus.WARNING
        if quality_flags or "low" in evidence_summary.confidence_labels
        else RadarSignalAgentAssessmentStatus.OK
    )
    findings = [
        f"Evidence items summarized: {evidence_summary.evidence_count}.",
        *[f"Freshness bucket: {label}." for label in evidence_summary.freshness_labels],
        *[f"Confidence bucket: {label}." for label in evidence_summary.confidence_labels],
        *[f"Quality flag: {flag}." for flag in quality_flags],
    ]
    return _agent_assessment(
        agent_id="data_quality_agent",
        label="Data Quality Agent",
        status=status,
        summary=(
            "Data quality needs review before downstream publication."
            if status == RadarSignalAgentAssessmentStatus.WARNING
            else "Data quality buckets do not show a current blocker."
        ),
        findings=findings,
        next_actions=[
            "Refresh provider snapshots if data quality flags remain.",
            "Keep confidence as a bucketed review signal only.",
        ],
    )


def _risk_agent_assessment(
    review_summary: RadarSignalReviewSummaryRead,
    risk_flags: list[str],
) -> RadarSignalAgentAssessmentRead:
    if review_summary.status == RadarReviewStatus.BLOCKED:
        status = RadarSignalAgentAssessmentStatus.BLOCKED
        summary = "Review blockers must be resolved before report or sharing workflow."
    elif risk_flags or review_summary.human_review_required:
        status = RadarSignalAgentAssessmentStatus.WARNING
        summary = "Risk flags or review gates require manual attention."
    else:
        status = RadarSignalAgentAssessmentStatus.OK
        summary = "No current review blocker is exposed by the analysis contract."

    findings = [
        f"Review status: {review_summary.status}.",
        *[f"Risk flag: {flag}." for flag in risk_flags],
    ]
    if review_summary.human_review_required:
        findings.append("Human review is required before report, push, or public sharing.")

    return _agent_assessment(
        agent_id="risk_agent",
        label="Risk Agent",
        status=status,
        summary=summary,
        findings=findings,
        next_actions=[
            "Resolve review blockers before report or sharing workflow.",
            "Keep risk output framed as research review, not trading instruction.",
        ],
    )


def _momentum_agent_assessment(
    signal: RadarSignal,
    metric_highlights: list[RadarSignalMetricHighlightRead],
) -> RadarSignalAgentAssessmentRead:
    continuity = signal.metrics.get("continuity")
    has_continuity = (
        isinstance(continuity, dict) and continuity.get("quick_report_candidate") is True
    )
    status = (
        RadarSignalAgentAssessmentStatus.WARNING
        if has_continuity
        else RadarSignalAgentAssessmentStatus.OK
    )
    findings = [
        f"Backend rule priority remains {signal.priority}.",
        f"Lifecycle stage remains {signal.lifecycle_stage}.",
        *[f"Metric context: {highlight.label}." for highlight in metric_highlights],
    ]
    if has_continuity:
        findings.append("Continuity context marks the signal for follow-up review.")

    return _agent_assessment(
        agent_id="momentum_agent",
        label="Momentum Agent",
        status=status,
        summary=(
            "Continuity context needs follow-up against the next scan."
            if has_continuity
            else "Priority and lifecycle context are present for review."
        ),
        findings=findings,
        next_actions=[
            "Compare the next scan with the current continuity context.",
            "Do not recalculate backend priority or lifecycle from this assessment.",
        ],
    )


def _evidence_agent_assessment(
    evidence_summary: RadarSignalEvidenceSummaryRead,
) -> RadarSignalAgentAssessmentRead:
    if evidence_summary.evidence_count == 0:
        status = RadarSignalAgentAssessmentStatus.WARNING
        summary = "No evidence summary is available for this signal."
    elif "low" in evidence_summary.confidence_labels:
        status = RadarSignalAgentAssessmentStatus.WARNING
        summary = "Evidence exists, but confidence buckets need review."
    else:
        status = RadarSignalAgentAssessmentStatus.OK
        summary = "Evidence summaries are available in the safe bounded contract."

    findings = [
        f"Evidence items summarized: {evidence_summary.evidence_count}.",
        *[f"Evidence type: {label}." for label in evidence_summary.evidence_types],
        *evidence_summary.summaries,
    ]

    return _agent_assessment(
        agent_id="evidence_agent",
        label="Evidence Agent",
        status=status,
        summary=summary,
        findings=findings,
        next_actions=[
            "Review bounded evidence summaries before report generation.",
            "Refresh source snapshots if evidence buckets become stale or missing.",
        ],
    )


def _report_agent_assessment(
    review_summary: RadarSignalReviewSummaryRead,
    next_actions: list[str],
) -> RadarSignalAgentAssessmentRead:
    if review_summary.status == RadarReviewStatus.BLOCKED:
        status = RadarSignalAgentAssessmentStatus.BLOCKED
        summary = "Report workflow is blocked by the current review state."
    elif review_summary.human_review_required:
        status = RadarSignalAgentAssessmentStatus.WARNING
        summary = "Report workflow needs human review before any outward-facing use."
    else:
        status = RadarSignalAgentAssessmentStatus.OK
        summary = "Report workflow can follow the existing approved review gate."

    return _agent_assessment(
        agent_id="report_agent",
        label="Report Agent",
        status=status,
        summary=summary,
        findings=[
            f"Review status: {review_summary.status}.",
            "Analysis output remains a research brief, not a recommendation layer.",
        ],
        next_actions=next_actions,
    )


def _agent_assessment(
    *,
    agent_id: str,
    label: str,
    status: RadarSignalAgentAssessmentStatus,
    summary: str,
    findings: list[str],
    next_actions: list[str],
) -> RadarSignalAgentAssessmentRead:
    return RadarSignalAgentAssessmentRead(
        agent_id=_analysis_text(agent_id),
        label=_analysis_text(label),
        status=status,
        summary=_analysis_text(summary),
        findings=_bounded_unique(findings, MAX_ANALYSIS_AGENT_FINDINGS),
        next_actions=_bounded_unique(next_actions, MAX_ANALYSIS_AGENT_FINDINGS),
    )


def _analysis_next_actions(
    signal: RadarSignal,
    review_summary: RadarSignalReviewSummaryRead,
) -> list[str]:
    actions: list[str] = []

    if review_summary.status == RadarReviewStatus.BLOCKED:
        actions.append("Resolve review blockers before any report, push, or public sharing.")
    elif review_summary.status == RadarReviewStatus.NEEDS_HUMAN_REVIEW:
        actions.append("Run manual research review before publishing or pushing this signal.")
    elif review_summary.status == RadarReviewStatus.CANDIDATE:
        actions.append("Run the lightweight review step before report, push, or public sharing.")
    else:
        actions.append("Use the approved review state as the publication gate.")

    continuity = signal.metrics.get("continuity")
    if isinstance(continuity, dict) and continuity.get("quick_report_candidate") is True:
        actions.append("Compare the next scan with the current continuity context.")

    if signal.priority == RadarPriority.P2.value:
        actions.append("Keep the signal in the observation window for delayed fermentation review.")
    else:
        actions.append("Refresh provider snapshots before escalating the research workflow.")

    actions.append("Keep output framed as personal research and risk review.")
    return _bounded_unique(actions, 5)


def _analysis_text(text: object, max_length: int = MAX_ANALYSIS_TEXT_LENGTH) -> str:
    redacted = redact_source_locators(_text(text, ""))
    return truncate_text(redacted, max_length)


def _bounded_unique(items: list[str], limit: int) -> list[str]:
    values: list[str] = []
    for item in items:
        cleaned = _analysis_text(item)
        if not cleaned or cleaned in values:
            continue
        values.append(cleaned)
        if len(values) >= limit:
            break
    return values


def _evidence_type_label(evidence_type: str) -> str:
    labels = {
        "market_snapshot": "market snapshot",
        "sector_snapshot": "sector snapshot",
        "concept_snapshot": "concept snapshot",
        "news": "event summary",
        "announcement": "announcement summary",
    }
    return labels.get(evidence_type, "evidence summary")


def _confidence_label(confidence: float) -> str:
    if confidence >= 0.8:
        return "high"
    if confidence >= 0.5:
        return "medium"
    return "low"


def _freshness_label(freshness: str) -> str:
    normalized = freshness.strip().lower()
    if any(marker in normalized for marker in ("stale", "expired", "outdated", "too_old")):
        return "possibly stale"
    if any(marker in normalized for marker in ("latest", "fresh", "current", "realtime")):
        return "fresh"
    if "unknown" in normalized or "no_source_time" in normalized:
        return "unknown"
    return "needs confirmation"


async def _load_latest_source_snapshots(session: AsyncSession) -> list[MarketSnapshot]:
    snapshots: list[MarketSnapshot] = []

    for endpoint in RADAR_SOURCE_ENDPOINTS:
        statement = (
            select(MarketSnapshot)
            .where(
                MarketSnapshot.provider_name.in_(_source_provider_names(endpoint)),
                MarketSnapshot.endpoint == endpoint,
            )
            .order_by(desc(MarketSnapshot.collected_at), desc(MarketSnapshot.id))
            .limit(1)
        )
        snapshot = await session.scalar(statement)
        if snapshot is not None:
            snapshots.append(snapshot)

    return snapshots


def _source_provider_names(endpoint: str) -> tuple[str, ...]:
    if endpoint in TUSHARE_ANNOUNCEMENT_SOURCE_ENDPOINTS:
        return ("tushare",)

    return RADAR_SOURCE_PROVIDER_NAMES


async def _load_snapshot_quality_summaries(
    session: AsyncSession,
    snapshots: list[MarketSnapshot],
) -> dict[int, dict[str, object]]:
    summaries: dict[int, dict[str, object]] = {}

    for snapshot in snapshots:
        snapshot_quality_check = await _latest_snapshot_quality_check(session, snapshot.id)
        endpoint_quality_check = await _latest_endpoint_quality_check(session, snapshot)
        summaries[snapshot.id] = _snapshot_quality_summary(
            snapshot,
            snapshot_quality_check,
            endpoint_quality_check,
        )

    return summaries


async def _latest_snapshot_quality_check(
    session: AsyncSession,
    snapshot_id: int,
) -> DataQualityCheck | None:
    statement = (
        select(DataQualityCheck)
        .where(DataQualityCheck.snapshot_id == snapshot_id)
        .order_by(desc(DataQualityCheck.created_at), desc(DataQualityCheck.id))
        .limit(1)
    )
    return await session.scalar(statement)


async def _latest_endpoint_quality_check(
    session: AsyncSession,
    snapshot: MarketSnapshot,
) -> DataQualityCheck | None:
    statement = (
        select(DataQualityCheck)
        .where(
            DataQualityCheck.provider_name == snapshot.provider_name,
            DataQualityCheck.endpoint == snapshot.endpoint,
        )
        .order_by(desc(DataQualityCheck.created_at), desc(DataQualityCheck.id))
        .limit(1)
    )
    return await session.scalar(statement)


async def _scan_read(
    session: AsyncSession,
    batch: RadarScanBatch,
) -> RadarScanRead:
    signal_statement = (
        select(RadarSignal)
        .where(RadarSignal.batch_id == batch.id)
        .order_by(desc(RadarSignal.created_at), desc(RadarSignal.id))
    )
    signals = (await session.scalars(signal_statement)).all()
    batch_data = RadarScanRead.model_validate(batch).model_dump(exclude={"signals"})
    return RadarScanRead(
        **batch_data,
        signals=[RadarSignalRead.model_validate(signal) for signal in signals],
    )


def _dedupe_subject_signals(signals: list[RadarSignalRead]) -> list[RadarSignalRead]:
    seen: set[str] = set()
    deduped: list[RadarSignalRead] = []

    for signal in signals:
        if signal.signal_key in seen:
            continue

        seen.add(signal.signal_key)
        deduped.append(signal)

    return deduped


def _filter_visible_signals(
    signals: list[RadarSignalRead],
    *,
    as_of: datetime | None = None,
) -> list[RadarSignalRead]:
    cutoff = _p2_observation_cutoff(as_of)
    return [
        signal
        for signal in signals
        if signal.priority != RadarPriority.P2 or _as_utc(signal.created_at) >= cutoff
    ]


def _p2_observation_cutoff(as_of: datetime | None = None) -> datetime:
    reference_time = _as_utc(as_of or datetime.now(UTC))
    return reference_time - timedelta(days=P2_OBSERVATION_WINDOW_DAYS)


def _scan_success_summary(
    source_endpoints: list[str],
    source_snapshot_count: int,
    snapshot_quality_summaries: dict[int, dict[str, object]],
    candidates: list[SignalCandidate],
    continuities: list[CandidateContinuity],
    market_sentiment: dict[str, object],
) -> dict[str, object]:
    return {
        "source_endpoints": source_endpoints,
        "source_snapshot_count": source_snapshot_count,
        "data_quality": _scan_data_quality_summary(snapshot_quality_summaries),
        "market_sentiment": market_sentiment,
        "candidate_count": len(candidates),
        "priority_counts": _priority_counts(candidates),
        "continuity_tracked_count": sum(
            1 for continuity in continuities if continuity.previous_signal_id is not None
        ),
        "quick_report_candidate_count": sum(
            1 for continuity in continuities if continuity.quick_report_candidate
        ),
        "lifecycle_transition_counts": _lifecycle_transition_counts(continuities),
        "max_signals_per_scan": MAX_SIGNALS_PER_SCAN,
        "continuous_p1_trigger_count": _continuous_p1_trigger_count(),
        "continuity_window_minutes": _continuity_window_minutes(),
    }


def _scan_failure_summary(
    source_endpoints: list[str],
    source_snapshot_count: int,
    snapshot_quality_summaries: dict[int, dict[str, object]],
    candidates: list[SignalCandidate],
    continuities: list[CandidateContinuity],
    exc: Exception,
    error_message: str,
) -> dict[str, object]:
    return {
        "source_endpoints": source_endpoints,
        "source_snapshot_count": source_snapshot_count,
        "data_quality": _scan_data_quality_summary(snapshot_quality_summaries),
        "candidate_count": len(candidates),
        "processed_candidate_count": len(continuities),
        "error_type": exc.__class__.__name__,
        "error_message": error_message,
    }


async def _record_scan_failure(
    session: AsyncSession,
    batch_id: int,
    source_snapshot_ids: list[int],
    source_endpoints: list[str],
    snapshot_quality_summaries: dict[int, dict[str, object]],
    candidates: list[SignalCandidate],
    continuities: list[CandidateContinuity],
    exc: Exception,
) -> None:
    await session.rollback()
    failure_batch = await session.get(RadarScanBatch, batch_id)
    if failure_batch is None:
        raise RuntimeError("radar scan failed and the batch could not be reloaded") from exc

    error_message = _short_error_message(exc)
    failure_batch.status = RadarScanStatus.FAILURE.value
    failure_batch.finished_at = datetime.now(UTC)
    failure_batch.source_snapshot_ids = source_snapshot_ids
    failure_batch.error_message = error_message
    failure_batch.summary = _scan_failure_summary(
        source_endpoints=source_endpoints,
        source_snapshot_count=len(source_snapshot_ids),
        snapshot_quality_summaries=snapshot_quality_summaries,
        candidates=candidates,
        continuities=continuities,
        exc=exc,
        error_message=error_message,
    )
    await session.commit()


async def _best_effort_record_scan_failure(
    session: AsyncSession,
    batch_id: int,
    source_snapshot_ids: list[int],
    source_endpoints: list[str],
    snapshot_quality_summaries: dict[int, dict[str, object]],
    candidates: list[SignalCandidate],
    continuities: list[CandidateContinuity],
    exc: SQLAlchemyError,
) -> None:
    try:
        await session.rollback()
        failure_batch = await session.get(RadarScanBatch, batch_id)
        if failure_batch is None or failure_batch.status != RadarScanStatus.RUNNING.value:
            return

        error_message = _short_error_message(exc)
        failure_batch.status = RadarScanStatus.FAILURE.value
        failure_batch.finished_at = datetime.now(UTC)
        failure_batch.source_snapshot_ids = source_snapshot_ids
        failure_batch.error_message = error_message
        failure_batch.summary = _scan_failure_summary(
            source_endpoints=source_endpoints,
            source_snapshot_count=len(source_snapshot_ids),
            snapshot_quality_summaries=snapshot_quality_summaries,
            candidates=candidates,
            continuities=continuities,
            exc=exc,
            error_message=error_message,
        )
        await session.commit()
    except Exception:
        with suppress(Exception):
            await session.rollback()


def _short_error_message(exc: Exception) -> str:
    error_type = exc.__class__.__name__
    detail = str(exc).strip()
    message = f"{error_type}: {detail}" if detail else error_type
    if len(message) <= MAX_ERROR_MESSAGE_LENGTH:
        return message

    return f"{message[: MAX_ERROR_MESSAGE_LENGTH - 3]}..."


def _build_signal_candidates(
    snapshots: list[MarketSnapshot],
    snapshot_quality_summaries: dict[int, dict[str, object]] | None = None,
    market_sentiment: dict[str, object] | None = None,
) -> list[SignalCandidate]:
    candidates: list[SignalCandidate] = []
    quality_summaries = snapshot_quality_summaries or {}
    sentiment_summary = market_sentiment or _empty_market_sentiment_summary()

    for snapshot in snapshots:
        data_quality = quality_summaries.get(
            snapshot.id,
            _snapshot_quality_summary(snapshot, None, None),
        )

        for row in snapshot.normalized_rows:
            metrics, rule_result = _classify_snapshot_row(
                snapshot,
                row,
                market_sentiment=sentiment_summary,
            )
            if rule_result is None:
                continue

            subject_name = _candidate_subject_name(snapshot, row)
            subject_code = _candidate_subject_code(row)
            candidates.append(
                SignalCandidate(
                    snapshot=snapshot,
                    row=row,
                    subject_type=snapshot.snapshot_type,
                    subject_code=subject_code,
                    subject_name=subject_name,
                    metrics=metrics,
                    data_quality=data_quality,
                    rule_result=rule_result,
                )
            )

    return sorted(candidates, key=_candidate_sort_key)[:MAX_SIGNALS_PER_SCAN]


async def _candidate_continuity(
    session: AsyncSession,
    candidate: SignalCandidate,
    scanned_at: datetime,
) -> CandidateContinuity:
    history = await _load_signal_history(session, _signal_key(candidate))
    previous = history[0] if history else None
    base_lifecycle = candidate.rule_result.lifecycle_stage
    adjusted_lifecycle = base_lifecycle
    transition = "new"
    reasons: list[str] = []
    previous_pct_change: float | None = None
    previous_breadth: float | None = None
    pct_change_delta: float | None = None
    breadth_delta: float | None = None

    if previous is not None:
        previous_pct_change = _float(previous.metrics.get("pct_change"))
        previous_breadth = _float(previous.metrics.get("breadth"))
        pct_change_delta = round(
            _float(candidate.metrics.get("pct_change")) - previous_pct_change,
            4,
        )
        breadth_delta = round(
            _float(candidate.metrics.get("breadth")) - previous_breadth,
            4,
        )
        adjusted_lifecycle = _adjust_lifecycle(candidate, previous, pct_change_delta, breadth_delta)
        transition = f"{previous.lifecycle_stage}_to_{adjusted_lifecycle.value}"

        if adjusted_lifecycle != base_lifecycle:
            reasons.append("lifecycle_adjusted_by_previous_scan")

    consecutive_p1_count = _consecutive_p1_count(history, candidate, scanned_at)
    quick_report_candidate = consecutive_p1_count >= _continuous_p1_trigger_count()

    if quick_report_candidate:
        reasons.append("continuous_p1_trigger")

    return CandidateContinuity(
        previous_signal_id=previous.id if previous is not None else None,
        previous_priority=previous.priority if previous is not None else None,
        previous_lifecycle_stage=previous.lifecycle_stage if previous is not None else None,
        previous_pct_change=previous_pct_change,
        previous_breadth=previous_breadth,
        pct_change_delta=pct_change_delta,
        breadth_delta=breadth_delta,
        consecutive_p1_count=consecutive_p1_count,
        quick_report_candidate=quick_report_candidate,
        adjusted_lifecycle_stage=adjusted_lifecycle,
        lifecycle_transition=transition,
        continuity_reasons=reasons,
    )


async def _load_signal_history(
    session: AsyncSession,
    signal_key: str,
    limit: int = 10,
) -> list[RadarSignal]:
    statement = (
        select(RadarSignal)
        .where(RadarSignal.signal_key == signal_key)
        .order_by(desc(RadarSignal.created_at), desc(RadarSignal.id))
        .limit(limit)
    )
    return list((await session.scalars(statement)).all())


def _new_signal(
    batch_id: int,
    candidate: SignalCandidate,
    continuity: CandidateContinuity,
) -> RadarSignal:
    priority = candidate.rule_result.priority
    return RadarSignal(
        batch_id=batch_id,
        signal_key=_signal_key(candidate),
        subject_type=candidate.subject_type,
        subject_code=candidate.subject_code,
        subject_name=candidate.subject_name,
        priority=priority.value,
        lifecycle_stage=continuity.adjusted_lifecycle_stage.value,
        review_status=RadarReviewStatus.CANDIDATE.value,
        title=f"{priority.value} radar candidate: {candidate.subject_name}",
        summary=_signal_summary(candidate, continuity),
        metrics={
            **candidate.metrics,
            "rule_reasons": candidate.rule_result.reasons,
            "continuity": _continuity_metrics(continuity),
            "source_endpoint": candidate.snapshot.endpoint,
            "source_snapshot_id": candidate.snapshot.id,
            "provider_quality": candidate.data_quality,
        },
        evidence_count=0,
    )


def _new_evidence(
    signal_id: int,
    candidate: SignalCandidate,
    continuity: CandidateContinuity,
) -> SignalEvidence:
    if _is_risk_event_candidate(candidate):
        return _new_risk_event_evidence(signal_id, candidate, continuity)

    pct_change = candidate.metrics["pct_change"]
    rising_count = candidate.metrics["rising_count"]
    falling_count = candidate.metrics["falling_count"]
    leading_stock = candidate.metrics.get("leading_stock")
    raw_excerpt = (
        f"{candidate.subject_name}: pct_change={pct_change}, "
        f"rising_count={rising_count}, falling_count={falling_count}, "
        f"leading_stock={leading_stock}"
    )
    return SignalEvidence(
        signal_id=signal_id,
        evidence_type="market_snapshot",
        source_name="akshare",
        source_ref=f"market_snapshot:{candidate.snapshot.id}",
        source_time=candidate.snapshot.source_time,
        collected_at=candidate.snapshot.collected_at,
        raw_excerpt=raw_excerpt,
        normalized_summary=(
            "Provider snapshot shows positive sector movement with breadth metrics."
        ),
        confidence=candidate.rule_result.confidence,
        freshness="snapshot_latest",
        details={
            "endpoint": candidate.snapshot.endpoint,
            "snapshot_type": candidate.snapshot.snapshot_type,
            "metrics": candidate.metrics,
            "rule_reasons": candidate.rule_result.reasons,
            "continuity": _continuity_metrics(continuity),
            "provider_quality": candidate.data_quality,
        },
        public_share_policy="internal_summary_only",
    )


def _row_metrics(row: dict[str, object]) -> dict[str, object]:
    rising_count = _int(row.get("rising_count"))
    falling_count = _int(row.get("falling_count"))
    total = rising_count + falling_count
    breadth = round(rising_count / total, 4) if total > 0 else 0.0

    return {
        "pct_change": _float(row.get("pct_change")),
        "turnover_rate": _float(row.get("turnover_rate")),
        "rising_count": rising_count,
        "falling_count": falling_count,
        "breadth": breadth,
        "leading_stock": row.get("leading_stock"),
        "leading_stock_pct_change": _float(row.get("leading_stock_pct_change")),
    }


def _risk_row_metrics(row: dict[str, object]) -> dict[str, object]:
    return {
        "risk_event_type": _text(
            row.get("risk_event_type") or row.get("event_type") or row.get("category"),
            "",
        ),
        "severity": _text(row.get("severity") or row.get("risk_level"), ""),
        "severity_score": _float(row.get("severity_score") or row.get("impact_score")),
        "source_label": _text(row.get("source_label") or row.get("source"), ""),
    }


def _announcement_risk_row_metrics(row: dict[str, object]) -> dict[str, object]:
    title = _text(row.get("title") or row.get("announcement_title"), "")
    matched_keywords = [
        keyword for keyword in MAJOR_RISK_ANNOUNCEMENT_KEYWORDS if keyword in title
    ]
    critical_matched = any(
        keyword in title for keyword in CRITICAL_RISK_ANNOUNCEMENT_KEYWORDS
    )

    base_metrics = {
        "source_label": "tushare:anns_d",
        "announcement_title": title,
        "announcement_keywords": matched_keywords,
        "ts_code": _text(row.get("ts_code"), ""),
        "stock_name": _text(row.get("name"), ""),
        "ann_date": _text(row.get("ann_date"), ""),
    }

    if not matched_keywords:
        return {
            **base_metrics,
            "risk_event_type": "",
            "severity": "",
            "severity_score": 0.0,
        }

    return {
        **base_metrics,
        "risk_event_type": "major_announcement",
        "severity": "critical" if critical_matched else "major",
        "severity_score": 0.92 if critical_matched else 0.88,
    }


def classify_tushare_announcement_risk(
    row: dict[str, object],
) -> tuple[dict[str, object], RadarRuleResult | None]:
    metrics = _announcement_risk_row_metrics(row)
    return metrics, classify_risk_event(metrics)


def _classify_snapshot_row(
    snapshot: MarketSnapshot,
    row: dict[str, object],
    *,
    market_sentiment: dict[str, object],
) -> tuple[dict[str, object], RadarRuleResult | None]:
    if _is_risk_event_snapshot(snapshot):
        metrics = _risk_row_metrics(row)
        return metrics, classify_risk_event(metrics)

    if _is_tushare_announcement_snapshot(snapshot):
        return classify_tushare_announcement_risk(row)

    if _is_market_mainline_snapshot(snapshot):
        metrics = _row_metrics(row)
        metrics["market_sentiment"] = market_sentiment
        if market_sentiment.get("sentiment_bias") == "positive":
            metrics["sentiment_confirmation"] = "positive_limit_up_pressure"
        return metrics, classify_sector_movement(metrics)

    return {}, None


def _candidate_subject_name(snapshot: MarketSnapshot, row: dict[str, object]) -> str:
    if _is_risk_source_snapshot(snapshot):
        return _text(
            row.get("event_name")
            or row.get("announcement_title")
            or row.get("title")
            or row.get("name"),
            "unknown risk event",
        )

    return _text(row.get("sector_name") or row.get("name"), "unknown")


def _candidate_subject_code(row: dict[str, object]) -> str | None:
    return _optional_text(
        row.get("sector_code")
        or row.get("event_id")
        or row.get("announcement_id")
        or row.get("ts_code")
        or row.get("symbol")
    )


def _candidate_sort_key(candidate: SignalCandidate) -> tuple[int, float, float]:
    priority_rank = {
        RadarPriority.P0: 0,
        RadarPriority.P1: 1,
        RadarPriority.P2: 2,
    }[candidate.rule_result.priority]
    strength = float(
        candidate.metrics.get("pct_change") or candidate.metrics.get("severity_score") or 0
    )
    breadth = float(
        candidate.metrics.get("breadth") or candidate.metrics.get("severity_score") or 0
    )
    return (
        priority_rank,
        -strength,
        -breadth,
    )


def _signal_key(candidate: SignalCandidate) -> str:
    subject_ref = candidate.subject_code or candidate.subject_name
    return f"{candidate.snapshot.provider_name}:{candidate.snapshot.endpoint}:{subject_ref}"


def _signal_summary(candidate: SignalCandidate, continuity: CandidateContinuity) -> str:
    if _is_risk_event_candidate(candidate):
        return (
            "Risk event candidate detected from the latest provider snapshot. "
            "Use it as research attention, not as trading advice."
        )

    summary = (
        "Sector movement detected from the latest provider snapshot. "
        "Use it as research attention, not as trading advice."
    )

    if continuity.quick_report_candidate:
        return (
            f"{summary} This subject has reached {continuity.consecutive_p1_count} "
            "consecutive P1 scans and is a quick-report candidate."
        )

    if continuity.previous_signal_id is not None:
        return f"{summary} Continuity was compared with the previous scan."

    return summary


def _new_risk_event_evidence(
    signal_id: int,
    candidate: SignalCandidate,
    continuity: CandidateContinuity,
) -> SignalEvidence:
    risk_event_type = candidate.metrics.get("risk_event_type")
    severity = candidate.metrics.get("severity")
    severity_score = candidate.metrics.get("severity_score")
    raw_excerpt = (
        f"{candidate.subject_name}: risk_event_type={risk_event_type}, "
        f"severity={severity}, severity_score={severity_score}"
    )
    return SignalEvidence(
        signal_id=signal_id,
        evidence_type="risk_event",
        source_name=candidate.snapshot.provider_name,
        source_ref=f"market_snapshot:{candidate.snapshot.id}",
        source_time=candidate.snapshot.source_time,
        collected_at=candidate.snapshot.collected_at,
        raw_excerpt=raw_excerpt,
        normalized_summary="Provider snapshot describes a major risk event.",
        confidence=candidate.rule_result.confidence,
        freshness="snapshot_latest",
        details={
            "endpoint": candidate.snapshot.endpoint,
            "snapshot_type": candidate.snapshot.snapshot_type,
            "metrics": candidate.metrics,
            "rule_reasons": candidate.rule_result.reasons,
            "continuity": _continuity_metrics(continuity),
            "provider_quality": candidate.data_quality,
        },
        public_share_policy="internal_summary_only",
    )


def _is_market_mainline_snapshot(snapshot: MarketSnapshot) -> bool:
    return snapshot.endpoint in MARKET_MAINLINE_SOURCE_ENDPOINTS


def _is_risk_event_snapshot(snapshot: MarketSnapshot) -> bool:
    return snapshot.endpoint in RISK_EVENT_SOURCE_ENDPOINTS


def _is_tushare_announcement_snapshot(snapshot: MarketSnapshot) -> bool:
    return (
        snapshot.provider_name == "tushare"
        and snapshot.endpoint in TUSHARE_ANNOUNCEMENT_SOURCE_ENDPOINTS
    )


def _is_risk_source_snapshot(snapshot: MarketSnapshot) -> bool:
    return _is_risk_event_snapshot(snapshot) or _is_tushare_announcement_snapshot(snapshot)


def _is_sentiment_snapshot(snapshot: MarketSnapshot) -> bool:
    return snapshot.endpoint in SENTIMENT_SOURCE_ENDPOINTS


def _is_risk_event_candidate(candidate: SignalCandidate) -> bool:
    return _is_risk_source_snapshot(candidate.snapshot)


def _market_sentiment_summary(snapshots: list[MarketSnapshot]) -> dict[str, object]:
    counts = {
        snapshot.endpoint: snapshot.row_count
        for snapshot in snapshots
        if _is_sentiment_snapshot(snapshot)
    }
    limit_up_count = counts.get("stock_zt_pool_em", 0)
    limit_down_count = counts.get("stock_zt_pool_dtgc_em", 0)
    broken_limit_up_count = counts.get("stock_zt_pool_zbgc_em", 0)

    return {
        "limit_up_count": limit_up_count,
        "limit_down_count": limit_down_count,
        "broken_limit_up_count": broken_limit_up_count,
        "net_limit_pressure": limit_up_count - limit_down_count - broken_limit_up_count,
        "sentiment_bias": _sentiment_bias(
            limit_up_count,
            limit_down_count,
            broken_limit_up_count,
        ),
    }


def _empty_market_sentiment_summary() -> dict[str, object]:
    return {
        "limit_up_count": 0,
        "limit_down_count": 0,
        "broken_limit_up_count": 0,
        "net_limit_pressure": 0,
        "sentiment_bias": "unknown",
    }


def _sentiment_bias(
    limit_up_count: int,
    limit_down_count: int,
    broken_limit_up_count: int,
) -> str:
    if limit_up_count <= 0 and limit_down_count <= 0 and broken_limit_up_count <= 0:
        return "unknown"

    if limit_up_count >= max(3, limit_down_count * 2) and limit_up_count > broken_limit_up_count:
        return "positive"

    if limit_down_count > limit_up_count:
        return "negative"

    return "mixed"


def _continuity_metrics(continuity: CandidateContinuity) -> dict[str, object]:
    return {
        "previous_signal_id": continuity.previous_signal_id,
        "previous_priority": continuity.previous_priority,
        "previous_lifecycle_stage": continuity.previous_lifecycle_stage,
        "previous_pct_change": continuity.previous_pct_change,
        "previous_breadth": continuity.previous_breadth,
        "pct_change_delta": continuity.pct_change_delta,
        "breadth_delta": continuity.breadth_delta,
        "consecutive_p1_count": continuity.consecutive_p1_count,
        "quick_report_candidate": continuity.quick_report_candidate,
        "lifecycle_transition": continuity.lifecycle_transition,
        "continuity_reasons": continuity.continuity_reasons,
    }


def _adjust_lifecycle(
    candidate: SignalCandidate,
    previous: RadarSignal,
    pct_change_delta: float,
    breadth_delta: float,
) -> RadarLifecycleStage:
    base_lifecycle = candidate.rule_result.lifecycle_stage
    current_priority = candidate.rule_result.priority
    previous_stage = previous.lifecycle_stage

    if previous_stage in {
        "divergence",
        "fading",
    } and pct_change_delta >= 1.0 and breadth_delta >= 0.05:
        return RadarLifecycleStage.RETURNING

    if pct_change_delta <= -2.0 or breadth_delta <= -0.2:
        if current_priority == RadarPriority.P2:
            return RadarLifecycleStage.FADING

        return RadarLifecycleStage.DIVERGENCE

    if (
        pct_change_delta >= 1.0
        and current_priority in {RadarPriority.P0, RadarPriority.P1}
        and base_lifecycle == RadarLifecycleStage.IGNITION
    ):
        return RadarLifecycleStage.DEVELOPING

    return base_lifecycle


def _consecutive_p1_count(
    history: list[RadarSignal],
    candidate: SignalCandidate,
    scanned_at: datetime,
) -> int:
    if candidate.rule_result.priority != RadarPriority.P1:
        return 0

    count = 1
    for signal in history:
        if signal.priority != RadarPriority.P1.value:
            break

        if not _within_continuity_window(signal.created_at, scanned_at):
            break

        count += 1

    return count


def _within_continuity_window(created_at: datetime, scanned_at: datetime) -> bool:
    return _as_utc(scanned_at) - _as_utc(created_at) <= timedelta(
        minutes=_continuity_window_minutes()
    )


def _continuous_p1_trigger_count() -> int:
    return get_settings().radar_continuous_p1_trigger_count


def _continuity_window_minutes() -> int:
    return get_settings().radar_continuity_window_minutes


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)

    return value.astimezone(UTC)


def _lifecycle_transition_counts(continuities: list[CandidateContinuity]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for continuity in continuities:
        counts[continuity.lifecycle_transition] = counts.get(continuity.lifecycle_transition, 0) + 1
    return counts


def _priority_counts(candidates: list[SignalCandidate]) -> dict[str, int]:
    counts = {priority.value: 0 for priority in RadarPriority}
    for candidate in candidates:
        counts[candidate.rule_result.priority.value] += 1
    return counts


def _signal_priority_counts(signals: list[RadarSignalRead]) -> dict[str, int]:
    counts = {priority.value: 0 for priority in RadarPriority}
    for signal in signals:
        counts[signal.priority.value] += 1
    return counts


def _signal_lifecycle_counts(signals: list[RadarSignalRead]) -> dict[str, int]:
    counts = {stage.value: 0 for stage in RadarLifecycleStage}
    for signal in signals:
        counts[signal.lifecycle_stage.value] += 1
    return counts


def _stock_backtrace_evidences(
    signals: list[RadarSignalRead],
) -> list[RadarStockBacktraceEvidenceRead]:
    evidences: list[RadarStockBacktraceEvidenceRead] = []

    for signal in signals:
        stock_name = _optional_text(signal.metrics.get("leading_stock"))
        stock_pct_change = _float(signal.metrics.get("leading_stock_pct_change"))
        if stock_name is None or stock_pct_change <= 0:
            continue

        evidences.append(
            RadarStockBacktraceEvidenceRead(
                signal_id=signal.id,
                subject_type=signal.subject_type,
                subject_code=signal.subject_code,
                subject_name=signal.subject_name,
                priority=signal.priority,
                lifecycle_stage=signal.lifecycle_stage,
                stock_name=stock_name,
                stock_pct_change=stock_pct_change,
                evidence_label=(
                    f"{stock_name} +{stock_pct_change:g}% -> {signal.subject_name}"
                ),
                source_snapshot_id=_optional_int(signal.metrics.get("source_snapshot_id")),
            )
        )

    return sorted(
        evidences,
        key=lambda evidence: (
            _priority_sort_rank(evidence.priority),
            -evidence.stock_pct_change,
            evidence.subject_name,
        ),
    )


def _snapshot_quality_summary(
    snapshot: MarketSnapshot,
    snapshot_quality_check: DataQualityCheck | None,
    endpoint_quality_check: DataQualityCheck | None,
) -> dict[str, object]:
    summary: dict[str, object] = {
        "snapshot_id": snapshot.id,
        "endpoint": snapshot.endpoint,
        "row_count": snapshot.row_count,
        "normalization_version": snapshot.normalization_version,
    }
    quality_check = _selected_quality_check(snapshot_quality_check, endpoint_quality_check)

    if quality_check is None:
        return {
            **summary,
            "status": "unknown",
            "confidence": None,
            "freshness": "unknown",
            "missing_fields": [],
            "quality_check_id": None,
            "fetch_log_id": None,
            "quality_scope": "missing",
            "snapshot_quality_status": None,
            "latest_endpoint_quality_status": None,
        }

    freshness = quality_check.details.get("freshness")
    return {
        **summary,
        "status": quality_check.status,
        "confidence": quality_check.confidence,
        "freshness": freshness if isinstance(freshness, str) else "unknown",
        "missing_fields": quality_check.missing_fields,
        "quality_check_id": quality_check.id,
        "fetch_log_id": quality_check.fetch_log_id,
        "quality_scope": _quality_scope(snapshot, quality_check),
        "snapshot_quality_status": (
            snapshot_quality_check.status if snapshot_quality_check is not None else None
        ),
        "latest_endpoint_quality_status": (
            endpoint_quality_check.status if endpoint_quality_check is not None else None
        ),
    }


def _selected_quality_check(
    snapshot_quality_check: DataQualityCheck | None,
    endpoint_quality_check: DataQualityCheck | None,
) -> DataQualityCheck | None:
    if endpoint_quality_check is not None and endpoint_quality_check.status == "failed":
        return endpoint_quality_check

    return snapshot_quality_check or endpoint_quality_check


def _quality_scope(
    snapshot: MarketSnapshot,
    quality_check: DataQualityCheck,
) -> str:
    if quality_check.snapshot_id == snapshot.id:
        return "snapshot"

    return "latest_endpoint"


def _scan_data_quality_summary(
    snapshot_quality_summaries: dict[int, dict[str, object]],
) -> dict[str, object]:
    status_counts: dict[str, int] = {}
    degraded_snapshot_ids: list[int] = []

    for snapshot_id, quality in snapshot_quality_summaries.items():
        status = str(quality.get("status") or "unknown")
        status_counts[status] = status_counts.get(status, 0) + 1

        if status != "ok":
            degraded_snapshot_ids.append(snapshot_id)

    return {
        "status_counts": status_counts,
        "degraded_snapshot_ids": degraded_snapshot_ids,
        "snapshots": list(snapshot_quality_summaries.values()),
    }


def _text(value: object, default: str) -> str:
    if value is None:
        return default

    text = str(value).strip()
    return text or default


def _optional_text(value: object) -> str | None:
    if value is None:
        return None

    text = str(value).strip()
    return text or None


def _float(value: object) -> float:
    if value is None:
        return 0.0

    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _int(value: object) -> int:
    if value is None:
        return 0

    try:
        return int(float(value))
    except (TypeError, ValueError):
        return 0


def _optional_int(value: object) -> int | None:
    if value is None:
        return None

    try:
        return int(float(value))
    except (TypeError, ValueError):
        return None


def _priority_sort_rank(priority: RadarPriority | str) -> int:
    return {
        RadarPriority.P0.value: 0,
        RadarPriority.P1.value: 1,
        RadarPriority.P2.value: 2,
    }.get(str(getattr(priority, "value", priority)), 99)
