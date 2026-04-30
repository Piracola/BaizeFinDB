from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.provider_models import MarketSnapshot
from app.db.radar_models import RadarScanBatch, RadarSignal, SignalEvidence
from app.radar.rules import RadarRuleResult, classify_sector_movement
from app.radar.schemas import (
    RadarPriority,
    RadarReviewStatus,
    RadarScanRead,
    RadarScanStatus,
    RadarSignalDetail,
    RadarSignalRead,
    SignalEvidenceRead,
)

RADAR_SOURCE_ENDPOINTS = (
    "stock_board_industry_name_em",
    "stock_board_concept_name_em",
)
MAX_SIGNALS_PER_SCAN = 20


@dataclass(frozen=True)
class SignalCandidate:
    snapshot: MarketSnapshot
    row: dict[str, object]
    subject_type: str
    subject_code: str | None
    subject_name: str
    metrics: dict[str, object]
    rule_result: RadarRuleResult


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

    snapshots = await _load_latest_source_snapshots(session)
    candidates = _build_signal_candidates(snapshots)

    for candidate in candidates:
        signal = _new_signal(batch.id, candidate)
        session.add(signal)
        await session.flush()

        session.add(_new_evidence(signal.id, candidate))
        signal.evidence_count = 1

    batch.status = (
        RadarScanStatus.SUCCESS.value if candidates else RadarScanStatus.NO_DATA.value
    )
    batch.finished_at = datetime.now(UTC)
    batch.source_snapshot_ids = [snapshot.id for snapshot in snapshots]
    batch.summary = {
        "source_endpoints": [snapshot.endpoint for snapshot in snapshots],
        "source_snapshot_count": len(snapshots),
        "candidate_count": len(candidates),
        "priority_counts": _priority_counts(candidates),
        "max_signals_per_scan": MAX_SIGNALS_PER_SCAN,
    }

    await session.commit()

    scan = await get_radar_scan(session, batch.id)
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


async def list_radar_signals(
    session: AsyncSession,
    priority: RadarPriority | None = None,
    limit: int = 50,
) -> list[RadarSignalRead]:
    statement = select(RadarSignal)

    if priority is not None:
        statement = statement.where(RadarSignal.priority == priority.value)

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


async def _load_latest_source_snapshots(session: AsyncSession) -> list[MarketSnapshot]:
    snapshots: list[MarketSnapshot] = []

    for endpoint in RADAR_SOURCE_ENDPOINTS:
        statement = (
            select(MarketSnapshot)
            .where(
                MarketSnapshot.provider_name == "akshare",
                MarketSnapshot.endpoint == endpoint,
            )
            .order_by(desc(MarketSnapshot.collected_at), desc(MarketSnapshot.id))
            .limit(1)
        )
        snapshot = await session.scalar(statement)
        if snapshot is not None:
            snapshots.append(snapshot)

    return snapshots


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


def _build_signal_candidates(snapshots: list[MarketSnapshot]) -> list[SignalCandidate]:
    candidates: list[SignalCandidate] = []

    for snapshot in snapshots:
        for row in snapshot.normalized_rows:
            metrics = _row_metrics(row)
            rule_result = classify_sector_movement(metrics)
            if rule_result is None:
                continue

            subject_name = _text(row.get("sector_name") or row.get("name"), "unknown")
            subject_code = _optional_text(row.get("sector_code") or row.get("symbol"))
            candidates.append(
                SignalCandidate(
                    snapshot=snapshot,
                    row=row,
                    subject_type=snapshot.snapshot_type,
                    subject_code=subject_code,
                    subject_name=subject_name,
                    metrics=metrics,
                    rule_result=rule_result,
                )
            )

    return sorted(candidates, key=_candidate_sort_key)[:MAX_SIGNALS_PER_SCAN]


def _new_signal(batch_id: int, candidate: SignalCandidate) -> RadarSignal:
    priority = candidate.rule_result.priority
    subject_ref = candidate.subject_code or candidate.subject_name
    return RadarSignal(
        batch_id=batch_id,
        signal_key=f"akshare:{candidate.snapshot.endpoint}:{subject_ref}",
        subject_type=candidate.subject_type,
        subject_code=candidate.subject_code,
        subject_name=candidate.subject_name,
        priority=priority.value,
        lifecycle_stage=candidate.rule_result.lifecycle_stage.value,
        review_status=RadarReviewStatus.CANDIDATE.value,
        title=f"{priority.value} radar candidate: {candidate.subject_name}",
        summary=(
            "Sector movement detected from the latest provider snapshot. "
            "Use it as research attention, not as trading advice."
        ),
        metrics={
            **candidate.metrics,
            "rule_reasons": candidate.rule_result.reasons,
            "source_endpoint": candidate.snapshot.endpoint,
            "source_snapshot_id": candidate.snapshot.id,
        },
        evidence_count=0,
    )


def _new_evidence(signal_id: int, candidate: SignalCandidate) -> SignalEvidence:
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


def _candidate_sort_key(candidate: SignalCandidate) -> tuple[int, float, float]:
    priority_rank = {
        RadarPriority.P0: 0,
        RadarPriority.P1: 1,
        RadarPriority.P2: 2,
    }[candidate.rule_result.priority]
    return (
        priority_rank,
        -float(candidate.metrics["pct_change"]),
        -float(candidate.metrics["breadth"]),
    )


def _priority_counts(candidates: list[SignalCandidate]) -> dict[str, int]:
    counts = {priority.value: 0 for priority in RadarPriority}
    for candidate in candidates:
        counts[candidate.rule_result.priority.value] += 1
    return counts


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
