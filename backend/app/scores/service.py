from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.radar_models import RadarSignal
from app.db.score_models import ScoreRecord
from app.scores.schemas import ScoreRecordRead, ScoreRunRead, ScoreStatus

SUPPORTED_SCORE_WINDOWS = (1, 3, 5, 10)
SCORING_VERSION = "m5_composite_v1"


async def generate_signal_scores(
    session: AsyncSession,
    signal_id: int,
    now: datetime | None = None,
) -> ScoreRunRead | None:
    signal = await session.get(RadarSignal, signal_id)
    if signal is None:
        return None

    evaluated_at = _as_utc(now or datetime.now(UTC))
    records: list[ScoreRecord] = []
    for window_days in SUPPORTED_SCORE_WINDOWS:
        score_status = _score_status(signal, window_days, evaluated_at)
        components = _score_components(signal)
        composite_score = _composite_score(components)
        details = {
            "scoring_version": SCORING_VERSION,
            "window_days": window_days,
            "window_complete": score_status == ScoreStatus.GENERATED,
            "window_end": (_as_utc(signal.created_at) + timedelta(days=window_days)).isoformat(),
            "method": "composite_without_price_only_backtest",
            "note": "Score combines priority, lifecycle, review, evidence and continuity signals.",
        }
        record = await _upsert_score_record(
            session=session,
            signal=signal,
            window_days=window_days,
            score_status=score_status,
            composite_score=composite_score,
            components=components,
            details=details,
            evaluated_at=evaluated_at,
        )
        records.append(record)

    await session.commit()
    for record in records:
        await session.refresh(record)

    return ScoreRunRead(
        signal_id=signal.id,
        records=[ScoreRecordRead.model_validate(record) for record in records],
    )


async def list_signal_scores(
    session: AsyncSession,
    signal_id: int,
) -> ScoreRunRead | None:
    signal = await session.get(RadarSignal, signal_id)
    if signal is None:
        return None

    statement = (
        select(ScoreRecord)
        .where(ScoreRecord.signal_id == signal_id)
        .order_by(ScoreRecord.window_days)
    )
    records = list((await session.scalars(statement)).all())
    return ScoreRunRead(
        signal_id=signal.id,
        records=[ScoreRecordRead.model_validate(record) for record in records],
    )


async def _upsert_score_record(
    session: AsyncSession,
    signal: RadarSignal,
    window_days: int,
    score_status: ScoreStatus,
    composite_score: float,
    components: dict[str, object],
    details: dict[str, object],
    evaluated_at: datetime,
) -> ScoreRecord:
    statement = select(ScoreRecord).where(
        ScoreRecord.signal_id == signal.id,
        ScoreRecord.window_days == window_days,
    )
    record = await session.scalar(statement)
    if record is None:
        record = ScoreRecord(
            signal_id=signal.id,
            window_days=window_days,
            score_status=score_status.value,
            composite_score=composite_score,
            components=components,
            details=details,
            evaluated_at=evaluated_at,
        )
        session.add(record)
        await session.flush()
        return record

    record.score_status = score_status.value
    record.composite_score = composite_score
    record.components = components
    record.details = details
    record.evaluated_at = evaluated_at
    await session.flush()
    return record


def _score_status(
    signal: RadarSignal,
    window_days: int,
    evaluated_at: datetime,
) -> ScoreStatus:
    window_end = _as_utc(signal.created_at) + timedelta(days=window_days)
    if evaluated_at >= window_end:
        return ScoreStatus.GENERATED

    return ScoreStatus.PENDING_WINDOW


def _score_components(signal: RadarSignal) -> dict[str, object]:
    return {
        "priority": _priority_score(signal.priority),
        "lifecycle": _lifecycle_score(signal.lifecycle_stage),
        "review": _review_score(signal.review_status),
        "evidence": _evidence_score(signal.evidence_count),
        "continuity": _continuity_score(signal.metrics),
    }


def _composite_score(components: dict[str, object]) -> float:
    weights = {
        "priority": 0.25,
        "lifecycle": 0.2,
        "review": 0.25,
        "evidence": 0.2,
        "continuity": 0.1,
    }
    score = sum(float(components[name]) * weight for name, weight in weights.items())
    return round(score, 2)


def _priority_score(priority: str) -> int:
    return {"P0": 85, "P1": 68, "P2": 45}.get(priority, 30)


def _lifecycle_score(lifecycle_stage: str) -> int:
    return {
        "ignition": 65,
        "developing": 78,
        "returning": 72,
        "climax": 58,
        "divergence": 45,
        "fading": 35,
        "extinguished": 25,
    }.get(lifecycle_stage, 40)


def _review_score(review_status: str) -> int:
    return {
        "approved": 82,
        "needs_human_review": 55,
        "candidate": 50,
        "blocked": 0,
    }.get(review_status, 40)


def _evidence_score(evidence_count: int) -> int:
    if evidence_count <= 0:
        return 0

    return min(90, 55 + evidence_count * 15)


def _continuity_score(metrics: dict[str, object]) -> int:
    continuity = metrics.get("continuity")
    if not isinstance(continuity, dict):
        return 45

    consecutive_count = _int(continuity.get("consecutive_p1_count"))
    base = min(80, 45 + consecutive_count * 10)
    if continuity.get("quick_report_candidate") is True:
        return max(base, 82)

    if continuity.get("previous_signal_id") is not None:
        return max(base, 60)

    return base


def _int(value: object) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)

    return value.astimezone(UTC)
