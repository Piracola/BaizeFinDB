from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.radar_models import RadarSignal
from app.db.score_models import ScoreRecord
from app.scores.schemas import ScoreRecordRead, ScoreRunRead, ScoreStatus

SUPPORTED_SCORE_WINDOWS = (1, 3, 5, 10)
SCORING_VERSION = "m5_composite_v2"
SCORING_METHOD = "calibrated_composite_without_price_only_backtest"
SCORING_WEIGHTS = {
    "priority": 0.22,
    "lifecycle": 0.16,
    "review": 0.2,
    "evidence": 0.16,
    "continuity": 0.12,
    "data_quality": 0.08,
    "timeliness": 0.06,
}


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
        components = _score_components(signal, evaluated_at)
        composite_score = _composite_score(components)
        details = {
            "scoring_version": SCORING_VERSION,
            "window_days": window_days,
            "window_complete": score_status == ScoreStatus.GENERATED,
            "window_end": (_as_utc(signal.created_at) + timedelta(days=window_days)).isoformat(),
            "method": SCORING_METHOD,
            "score_band": _score_band(composite_score),
            "weights": dict(SCORING_WEIGHTS),
            "calibration_inputs": {
                "provider_quality_status": _provider_quality_status(signal.metrics),
                "signal_age_hours": _signal_age_hours(signal.created_at, evaluated_at),
            },
            "note": (
                "Score combines priority, lifecycle, review, evidence, continuity, "
                "provider data quality and timeliness signals."
            ),
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


def _score_components(signal: RadarSignal, evaluated_at: datetime) -> dict[str, object]:
    return {
        "priority": _priority_score(signal.priority),
        "lifecycle": _lifecycle_score(signal.lifecycle_stage),
        "review": _review_score(signal.review_status),
        "evidence": _evidence_score(signal.evidence_count),
        "continuity": _continuity_score(signal.metrics),
        "data_quality": _data_quality_score(signal.metrics),
        "timeliness": _timeliness_score(signal.created_at, evaluated_at),
    }


def _composite_score(components: dict[str, object]) -> float:
    score = sum(
        float(components.get(name, 0)) * weight for name, weight in SCORING_WEIGHTS.items()
    )
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


def _data_quality_score(metrics: dict[str, object]) -> int:
    provider_quality = metrics.get("provider_quality")
    if not isinstance(provider_quality, dict):
        return 50

    status_score = {
        "ok": 82,
        "degraded": 45,
        "unknown": 50,
        "failed": 0,
    }.get(_provider_quality_status(metrics), 50)
    confidence = _optional_float(provider_quality.get("confidence"))
    confidence_score = status_score if confidence is None else round(_clamp(confidence, 0, 1) * 100)
    score = round(status_score * 0.6 + confidence_score * 0.4)

    missing_fields = provider_quality.get("missing_fields")
    if isinstance(missing_fields, list):
        score -= min(30, len(missing_fields) * 5)

    return _int_clamp(score, 0, 100)


def _timeliness_score(created_at: datetime, evaluated_at: datetime) -> int:
    age_hours = _signal_age_hours(created_at, evaluated_at)
    if age_hours <= 1:
        return 90
    if age_hours <= 6:
        return 82
    if age_hours <= 24:
        return 70
    if age_hours <= 72:
        return 58
    if age_hours <= 168:
        return 45
    if age_hours <= 240:
        return 35
    return 25


def _score_band(composite_score: float) -> str:
    if composite_score >= 75:
        return "strong_attention"
    if composite_score >= 60:
        return "watch"
    if composite_score >= 45:
        return "weak_watch"
    return "low_signal_quality"


def _provider_quality_status(metrics: dict[str, object]) -> str:
    provider_quality = metrics.get("provider_quality")
    if not isinstance(provider_quality, dict):
        return "unknown"

    status = provider_quality.get("status")
    return str(status).strip().lower() if status is not None else "unknown"


def _signal_age_hours(created_at: datetime, evaluated_at: datetime) -> float:
    elapsed = _as_utc(evaluated_at) - _as_utc(created_at)
    return round(max(0.0, elapsed.total_seconds() / 3600), 2)


def _int(value: object) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def _optional_float(value: object) -> float | None:
    if value is None:
        return None

    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _clamp(value: float, minimum: float, maximum: float) -> float:
    return min(max(value, minimum), maximum)


def _int_clamp(value: int, minimum: int, maximum: int) -> int:
    return min(max(value, minimum), maximum)


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)

    return value.astimezone(UTC)
