import json
import re
from collections import Counter
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.radar_models import RadarSignal, RadarSignalReview, SignalEvidence
from app.radar.schemas import RadarReviewStatus, RadarSignalReviewRead

REVIEWER_NAME = "lightweight_rule_review"
RULE_VERSION = "m4_lightweight_rules_v2"
LOW_CONFIDENCE_THRESHOLD = 0.5
PROVIDER_QUALITY_BLOCK_STATUSES = {"failed"}
PROVIDER_QUALITY_REVIEW_STATUSES = {"degraded", "unknown"}
STALE_SOURCE_MAX_AGE = timedelta(days=2)
STALE_SOURCE_FRESHNESS_MARKERS = (
    "stale",
    "expired",
    "outdated",
    "too_old",
    "数据过期",
    "来源过期",
)
EVIDENCE_CONFLICT_FIELDS = (
    "pct_change",
    "rising_count",
    "falling_count",
    "breadth",
    "leading_stock_pct_change",
)
EVIDENCE_CONFLICT_NUMERIC_TOLERANCE = 0.0001
DUPLICATE_HINT_FIELDS = (
    "rule_reasons",
    "review_reasons",
    "review_hints",
    "trigger_reasons",
    "triggers",
    "continuity_reasons",
)
SAFE_TRADING_LANGUAGE_PHRASES = (
    "不保证收益",
    "不构成投资建议",
    "不是投资建议",
    "不是交易建议",
    "不作为买卖建议",
    "不是买入信号",
    "不是卖出信号",
    "仅作研究关注",
    "仅供研究关注",
)
SAFE_TRADING_NEGATION_PREFIXES = (
    "不",
    "不要",
    "不能",
    "禁止",
    "避免",
    "切勿",
    "不可",
    "严禁",
    "拒绝",
    "别",
)
TEXT_SEPARATOR_PATTERN = re.compile(r"[\s,，。！？!?:：；;、（）()\[\]【】\"'“”‘’·\-_/]+")

FORBIDDEN_TRADING_TERMS = (
    "必涨",
    "必买",
    "立即买入",
    "马上买入",
    "推荐买入",
    "强烈推荐买入",
    "稳赚",
    "稳赚不赔",
    "满仓",
    "梭哈",
    "无脑上",
    "保证收益",
    "照单交易",
    "跟着买",
    "买入信号",
    "卖出信号",
    "闭眼冲",
    "翻倍票",
    "抄底加仓",
)


@dataclass(frozen=True)
class ReviewDecision:
    review_status: RadarReviewStatus
    reasons: list[str]
    details: dict[str, object]


async def review_radar_signal(
    session: AsyncSession,
    signal_id: int,
) -> RadarSignalReviewRead | None:
    signal = await session.get(RadarSignal, signal_id)
    if signal is None:
        return None

    evidences = await _load_signal_evidences(session, signal_id)
    decision = evaluate_radar_signal(signal, evidences)

    review = RadarSignalReview(
        signal_id=signal.id,
        review_status=decision.review_status.value,
        reviewer=REVIEWER_NAME,
        rule_version=RULE_VERSION,
        reasons=decision.reasons,
        details=decision.details,
    )
    signal.review_status = decision.review_status.value
    session.add(review)

    await session.commit()
    await session.refresh(review)
    return RadarSignalReviewRead.model_validate(review)


async def list_radar_signal_reviews(
    session: AsyncSession,
    signal_id: int,
) -> list[RadarSignalReviewRead] | None:
    signal = await session.get(RadarSignal, signal_id)
    if signal is None:
        return None

    statement = (
        select(RadarSignalReview)
        .where(RadarSignalReview.signal_id == signal_id)
        .order_by(desc(RadarSignalReview.created_at), desc(RadarSignalReview.id))
    )
    reviews = (await session.scalars(statement)).all()
    return [RadarSignalReviewRead.model_validate(review) for review in reviews]


def evaluate_radar_signal(
    signal: RadarSignal,
    evidences: Sequence[SignalEvidence],
) -> ReviewDecision:
    reasons = _priority_reasons(signal)
    details: dict[str, object] = {
        "evidence_count": signal.evidence_count,
        "actual_evidence_count": len(evidences),
        "low_confidence_threshold": LOW_CONFIDENCE_THRESHOLD,
    }

    matched_terms = _matched_forbidden_terms(signal, evidences)
    if matched_terms:
        reasons.append("forbidden_trading_language")
        details["matched_forbidden_terms"] = matched_terms

    if _has_missing_evidence(signal, evidences):
        reasons.append("missing_evidence")

    if _has_evidence_count_mismatch(signal, evidences):
        reasons.append("evidence_count_mismatch")

    confidences = [evidence.confidence for evidence in evidences]
    low_confidences = [
        confidence for confidence in confidences if confidence < LOW_CONFIDENCE_THRESHOLD
    ]
    if low_confidences:
        details["min_evidence_confidence"] = min(confidences)
        reasons.append("low_evidence_confidence")

    provider_quality_statuses = _provider_quality_statuses(signal, evidences)
    if provider_quality_statuses:
        details["provider_quality_statuses"] = sorted(provider_quality_statuses)

    if PROVIDER_QUALITY_BLOCK_STATUSES.intersection(provider_quality_statuses):
        reasons.append("failed_provider_quality")

    if PROVIDER_QUALITY_REVIEW_STATUSES.intersection(provider_quality_statuses):
        reasons.append("provider_quality_needs_review")

    evidence_conflicts = _evidence_conflicts(signal, evidences)
    if evidence_conflicts:
        reasons.append("evidence_conflict")
        details["evidence_conflicts"] = evidence_conflicts

    duplicate_hints = _duplicate_trigger_review_hints(signal, evidences)
    if duplicate_hints:
        reasons.append("duplicate_trigger_review_hints")
        details["duplicate_trigger_review_hints"] = duplicate_hints

    stale_sources = _stale_sources(evidences)
    if stale_sources:
        reasons.append("stale_source")
        details["stale_sources"] = stale_sources
        details["stale_source_max_age_hours"] = _hours(STALE_SOURCE_MAX_AGE)

    if (
        "forbidden_trading_language" in reasons
        or "missing_evidence" in reasons
        or "failed_provider_quality" in reasons
    ):
        review_status = RadarReviewStatus.BLOCKED
    elif (
        "low_evidence_confidence" in reasons
        or "evidence_count_mismatch" in reasons
        or "provider_quality_needs_review" in reasons
        or "evidence_conflict" in reasons
        or "duplicate_trigger_review_hints" in reasons
        or "stale_source" in reasons
    ):
        review_status = RadarReviewStatus.NEEDS_HUMAN_REVIEW
    else:
        review_status = RadarReviewStatus.APPROVED
        reasons.append("rule_review_passed")

    return ReviewDecision(
        review_status=review_status,
        reasons=_dedupe_reasons(reasons),
        details=details,
    )


async def _load_signal_evidences(
    session: AsyncSession,
    signal_id: int,
) -> list[SignalEvidence]:
    statement = (
        select(SignalEvidence)
        .where(SignalEvidence.signal_id == signal_id)
        .order_by(desc(SignalEvidence.created_at), desc(SignalEvidence.id))
    )
    return list((await session.scalars(statement)).all())


def _priority_reasons(signal: RadarSignal) -> list[str]:
    reasons: list[str] = []

    if signal.priority == "P0":
        reasons.append("high_priority_review")

    continuity = signal.metrics.get("continuity")
    if isinstance(continuity, dict) and continuity.get("quick_report_candidate") is True:
        reasons.append("quick_report_review")

    return reasons


def _matched_forbidden_terms(
    signal: RadarSignal,
    evidences: Sequence[SignalEvidence],
) -> list[str]:
    reviewable_text = _normalize_trading_language(
        _mask_safe_trading_language(_reviewable_text(signal, evidences))
    ).lower()
    matched_terms: list[str] = []

    for term in FORBIDDEN_TRADING_TERMS:
        normalized_term = _normalize_trading_language(term).lower()
        if normalized_term and _has_unsafe_term(reviewable_text, normalized_term):
            matched_terms.append(term)

    return matched_terms


def _mask_safe_trading_language(text: str) -> str:
    masked_text = text
    for phrase in SAFE_TRADING_LANGUAGE_PHRASES:
        masked_text = masked_text.replace(phrase, "")
    return masked_text


def _normalize_trading_language(text: str) -> str:
    return TEXT_SEPARATOR_PATTERN.sub("", text)


def _has_unsafe_term(text: str, term: str) -> bool:
    start = 0
    while True:
        index = text.find(term, start)
        if index < 0:
            return False
        if not _is_safely_negated(text, index):
            return True
        start = index + len(term)


def _is_safely_negated(text: str, term_start: int) -> bool:
    prefix_context = text[max(0, term_start - 8) : term_start]
    return any(
        prefix_context.endswith(prefix)
        for prefix in SAFE_TRADING_NEGATION_PREFIXES
    )


def _reviewable_text(
    signal: RadarSignal,
    evidences: Sequence[SignalEvidence],
) -> str:
    chunks = [
        signal.subject_name,
        signal.title,
        signal.summary,
        json.dumps(signal.metrics, ensure_ascii=False, default=str),
    ]

    for evidence in evidences:
        chunks.extend(
            [
                evidence.raw_excerpt,
                evidence.normalized_summary,
                json.dumps(evidence.details, ensure_ascii=False, default=str),
            ]
        )

    return "\n".join(chunks)


def _has_missing_evidence(signal: RadarSignal, evidences: Sequence[SignalEvidence]) -> bool:
    return len(evidences) == 0 or len(evidences) < signal.evidence_count


def _has_evidence_count_mismatch(
    signal: RadarSignal,
    evidences: Sequence[SignalEvidence],
) -> bool:
    return len(evidences) > 0 and signal.evidence_count != len(evidences)


def _provider_quality_statuses(
    signal: RadarSignal,
    evidences: Sequence[SignalEvidence],
) -> set[str]:
    statuses: set[str] = set()

    for quality in _provider_quality_items(signal, evidences):
        status = quality.get("status")
        if isinstance(status, str) and status:
            statuses.add(status)

    return statuses


def _provider_quality_items(
    signal: RadarSignal,
    evidences: Sequence[SignalEvidence],
) -> list[dict[str, object]]:
    items: list[dict[str, object]] = []

    signal_quality = signal.metrics.get("provider_quality")
    if isinstance(signal_quality, dict):
        items.append(signal_quality)

    for evidence in evidences:
        evidence_quality = evidence.details.get("provider_quality")
        if isinstance(evidence_quality, dict):
            items.append(evidence_quality)

    return items


def _evidence_conflicts(
    signal: RadarSignal,
    evidences: Sequence[SignalEvidence],
) -> list[dict[str, object]]:
    conflicts: list[dict[str, object]] = []

    for index, evidence in enumerate(evidences):
        conflicts.extend(_explicit_evidence_conflicts(index, evidence))

        evidence_metrics = evidence.details.get("metrics")
        if not isinstance(evidence_metrics, dict):
            continue

        for field in EVIDENCE_CONFLICT_FIELDS:
            if field not in signal.metrics or field not in evidence_metrics:
                continue

            signal_value = signal.metrics[field]
            evidence_value = evidence_metrics[field]
            if not _values_conflict(signal_value, evidence_value):
                continue

            conflicts.append(
                {
                    "evidence_index": index,
                    "source_name": evidence.source_name,
                    "source_ref": evidence.source_ref,
                    "field": field,
                    "signal_value": _detail_value(signal_value),
                    "evidence_value": _detail_value(evidence_value),
                }
            )

    return conflicts


def _explicit_evidence_conflicts(
    evidence_index: int,
    evidence: SignalEvidence,
) -> list[dict[str, object]]:
    conflicts: list[dict[str, object]] = []

    for flag_name in ("conflict", "evidence_conflict"):
        if evidence.details.get(flag_name) is True:
            conflicts.append(
                {
                    "evidence_index": evidence_index,
                    "source_name": evidence.source_name,
                    "source_ref": evidence.source_ref,
                    "field": flag_name,
                    "detail": True,
                }
            )

    for conflict_field in ("conflicts", "evidence_conflicts"):
        conflict_details = evidence.details.get(conflict_field)
        if isinstance(conflict_details, list) and conflict_details:
            conflicts.append(
                {
                    "evidence_index": evidence_index,
                    "source_name": evidence.source_name,
                    "source_ref": evidence.source_ref,
                    "field": conflict_field,
                    "detail": _detail_value(conflict_details),
                }
            )

    return conflicts


def _values_conflict(left: object, right: object) -> bool:
    left_number = _number_or_none(left)
    right_number = _number_or_none(right)
    if left_number is not None and right_number is not None:
        return abs(left_number - right_number) > EVIDENCE_CONFLICT_NUMERIC_TOLERANCE

    return str(left).strip() != str(right).strip()


def _number_or_none(value: object) -> float | None:
    if isinstance(value, bool):
        return None

    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _duplicate_trigger_review_hints(
    signal: RadarSignal,
    evidences: Sequence[SignalEvidence],
) -> list[dict[str, object]]:
    duplicates: list[dict[str, object]] = []

    for location, hints in _hint_lists(signal, evidences):
        clean_hints = [hint for hint in hints if hint]
        counts = Counter(clean_hints)
        for hint, count in sorted(counts.items()):
            if count <= 1:
                continue

            duplicates.append(
                {
                    "location": location,
                    "hint": hint,
                    "count": count,
                }
            )

    return duplicates


def _hint_lists(
    signal: RadarSignal,
    evidences: Sequence[SignalEvidence],
) -> list[tuple[str, list[str]]]:
    hint_lists = _hint_lists_from_mapping("signal.metrics", signal.metrics)

    for index, evidence in enumerate(evidences):
        hint_lists.extend(
            _hint_lists_from_mapping(f"evidence[{index}].details", evidence.details)
        )

    return hint_lists


def _hint_lists_from_mapping(
    location: str,
    mapping: dict[str, object],
) -> list[tuple[str, list[str]]]:
    hint_lists: list[tuple[str, list[str]]] = []

    for field in DUPLICATE_HINT_FIELDS:
        value = mapping.get(field)
        if isinstance(value, list):
            hints = [item for item in value if isinstance(item, str)]
            hint_lists.append((f"{location}.{field}", hints))

    for nested_field in ("continuity", "review", "governance"):
        nested = mapping.get(nested_field)
        if isinstance(nested, dict):
            hint_lists.extend(
                _hint_lists_from_mapping(f"{location}.{nested_field}", nested)
            )

    return hint_lists


def _stale_sources(evidences: Sequence[SignalEvidence]) -> list[dict[str, object]]:
    stale_sources: list[dict[str, object]] = []

    for index, evidence in enumerate(evidences):
        stale_reasons = _stale_source_reasons(evidence)
        if not stale_reasons:
            continue

        stale_source: dict[str, object] = {
            "evidence_index": index,
            "source_name": evidence.source_name,
            "source_ref": evidence.source_ref,
            "reasons": stale_reasons,
            "freshness": evidence.freshness,
        }
        age = _source_age(evidence)
        if age is not None:
            stale_source["source_age_hours"] = _hours(age)

        stale_sources.append(stale_source)

    return stale_sources


def _stale_source_reasons(evidence: SignalEvidence) -> list[str]:
    reasons: list[str] = []

    if _source_age_is_stale(evidence):
        reasons.append("source_time_older_than_collected_at")

    if any(_freshness_is_stale(value) for value in _freshness_values(evidence)):
        reasons.append("freshness_marked_stale")

    return reasons


def _source_age_is_stale(evidence: SignalEvidence) -> bool:
    age = _source_age(evidence)
    return age is not None and age > STALE_SOURCE_MAX_AGE


def _source_age(evidence: SignalEvidence) -> timedelta | None:
    if evidence.source_time is None:
        return None

    source_time = _as_utc(evidence.source_time)
    collected_at = _as_utc(evidence.collected_at)
    age = collected_at - source_time
    if age < timedelta(0):
        return None

    return age


def _freshness_values(evidence: SignalEvidence) -> list[object]:
    values: list[object] = [
        evidence.freshness,
        evidence.details.get("freshness"),
    ]

    provider_quality = evidence.details.get("provider_quality")
    if isinstance(provider_quality, dict):
        values.append(provider_quality.get("freshness"))

    return values


def _freshness_is_stale(value: object) -> bool:
    if not isinstance(value, str):
        return False

    normalized = value.strip().lower()
    return any(marker in normalized for marker in STALE_SOURCE_FRESHNESS_MARKERS)


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.tzinfo.utcoffset(value) is None:
        return value.replace(tzinfo=UTC)

    return value.astimezone(UTC)


def _hours(value: timedelta) -> float:
    return round(value.total_seconds() / 3600, 2)


def _detail_value(value: object) -> object:
    return json.loads(json.dumps(value, ensure_ascii=False, default=str))


def _dedupe_reasons(reasons: list[str]) -> list[str]:
    return list(dict.fromkeys(reasons))
