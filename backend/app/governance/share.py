import re
from collections.abc import Sequence

from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.radar_models import RadarSignal, RadarSignalReview, SignalEvidence
from app.radar.schemas import (
    RadarSignalPublicShareRead,
    RadarSignalShareEvidenceRead,
    RadarSignalSharePreviewRead,
    RadarSignalShareStatus,
)

MAX_SHARE_SUMMARY_LENGTH = 180
SAFE_SHARE_POLICIES = {"internal_summary_only", "public_summary"}
SHARE_DISCLAIMER = "仅供个人研究和复盘，不构成投资建议，不保证收益，用户需要自行决策并承担风险。"
URL_PATTERN = re.compile(r"https?://[^\s，。；;、)）]+|www\.[^\s，。；;、)）]+", re.IGNORECASE)
DOMAIN_PATTERN = re.compile(
    r"\b(?:[a-z0-9-]+\.)+[a-z]{2,24}\b",
    re.IGNORECASE,
)


async def get_radar_signal_share_preview(
    session: AsyncSession,
    signal_id: int,
) -> RadarSignalSharePreviewRead | None:
    signal = await session.get(RadarSignal, signal_id)
    if signal is None:
        return None

    evidences = await _load_signal_evidences(session, signal_id)
    latest_review = await _load_latest_review(session, signal_id)
    return build_signal_share_preview(signal, evidences, latest_review)


def build_signal_share_preview(
    signal: RadarSignal,
    evidences: Sequence[SignalEvidence],
    latest_review: RadarSignalReview | None,
) -> RadarSignalSharePreviewRead:
    blocked_reasons = _share_blocked_reasons(signal, evidences, latest_review)
    sanitization_notes: list[str] = [
        "source_locator_omitted",
        "source_label_omitted",
        "raw_text_omitted",
        "internal_metadata_omitted",
    ]

    share_status = (
        RadarSignalShareStatus.READY
        if not blocked_reasons
        else RadarSignalShareStatus.BLOCKED
    )

    share_evidences = [
        _share_evidence(evidence, sanitization_notes) for evidence in evidences
    ]
    title = _share_text(signal.title, MAX_SHARE_SUMMARY_LENGTH, sanitization_notes)
    summary = _share_text(signal.summary, MAX_SHARE_SUMMARY_LENGTH, sanitization_notes)
    public_payload = _public_share_payload(signal, title, summary, share_evidences)

    return RadarSignalSharePreviewRead(
        signal_id=signal.id,
        share_status=share_status,
        review_status=signal.review_status,
        latest_review_id=latest_review.id if latest_review is not None else None,
        blocked_reasons=blocked_reasons,
        sanitization_notes=list(dict.fromkeys(sanitization_notes)),
        title=title,
        summary=summary,
        subject_type=signal.subject_type,
        subject_code=signal.subject_code,
        subject_name=signal.subject_name,
        priority=signal.priority,
        lifecycle_stage=signal.lifecycle_stage,
        evidences=share_evidences,
        disclaimer=SHARE_DISCLAIMER,
        public_payload=public_payload,
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


async def _load_latest_review(
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


def _share_blocked_reasons(
    signal: RadarSignal,
    evidences: Sequence[SignalEvidence],
    latest_review: RadarSignalReview | None,
) -> list[str]:
    reasons: list[str] = []

    if latest_review is None:
        reasons.append("review_required")
    elif latest_review.review_status != "approved":
        reasons.append("latest_review_not_approved")

    if signal.review_status != "approved":
        reasons.append("signal_review_not_approved")

    unsafe_policies = sorted(
        {
            evidence.public_share_policy
            for evidence in evidences
            if evidence.public_share_policy not in SAFE_SHARE_POLICIES
        }
    )
    if unsafe_policies:
        reasons.append("unsafe_public_share_policy")

    if not evidences:
        reasons.append("missing_evidence")

    return list(dict.fromkeys(reasons))


def _share_evidence(
    evidence: SignalEvidence,
    sanitization_notes: list[str],
) -> RadarSignalShareEvidenceRead:
    summary = _share_text(
        evidence.normalized_summary,
        MAX_SHARE_SUMMARY_LENGTH,
        sanitization_notes,
    )
    if summary != evidence.normalized_summary:
        sanitization_notes.append("long_evidence_summary_truncated")

    sanitization_notes.extend(
        [
            "evidence_kind_mapped",
            "confidence_bucketed",
            "freshness_bucketed",
            "evidence_timestamp_omitted",
        ]
    )

    return RadarSignalShareEvidenceRead(
        summary=summary,
        evidence_label=_evidence_label(evidence.evidence_type),
        confidence_label=_confidence_label(evidence.confidence),
        freshness_label=_freshness_label(evidence.freshness),
    )


def _share_text(
    text: str,
    max_length: int,
    sanitization_notes: list[str],
) -> str:
    redacted = _redact_source_locators(text)
    if redacted != text:
        sanitization_notes.append("source_locator_redacted")

    return _truncate_text(redacted, max_length)


def _redact_source_locators(text: str) -> str:
    without_urls = URL_PATTERN.sub("[source omitted]", text)
    return DOMAIN_PATTERN.sub("[source omitted]", without_urls)


def _truncate_text(text: str, max_length: int) -> str:
    stripped = text.strip()
    if len(stripped) <= max_length:
        return stripped

    return f"{stripped[: max_length - 3].rstrip()}..."


def _public_share_payload(
    signal: RadarSignal,
    title: str,
    summary: str,
    evidences: list[RadarSignalShareEvidenceRead],
) -> RadarSignalPublicShareRead:
    return RadarSignalPublicShareRead(
        title=title,
        summary=summary,
        subject_name=signal.subject_name,
        priority_label=_priority_label(signal.priority),
        lifecycle_label=_lifecycle_label(signal.lifecycle_stage),
        evidences=evidences,
        disclaimer=SHARE_DISCLAIMER,
    )


def _evidence_label(evidence_type: str) -> str:
    labels = {
        "market_snapshot": "市场快照",
        "sector_snapshot": "板块快照",
        "concept_snapshot": "概念快照",
        "news": "事件摘要",
        "announcement": "公告摘要",
    }
    return labels.get(evidence_type, "证据摘要")


def _confidence_label(confidence: float) -> str:
    if confidence >= 0.8:
        return "高"
    if confidence >= 0.5:
        return "中"
    return "低"


def _freshness_label(freshness: str) -> str:
    normalized = freshness.strip().lower()
    if any(marker in normalized for marker in ("stale", "expired", "outdated", "too_old")):
        return "可能过期"
    if any(marker in normalized for marker in ("latest", "fresh", "current", "realtime")):
        return "较新"
    if "unknown" in normalized or "no_source_time" in normalized:
        return "未知"
    return "待确认"


def _priority_label(priority: str) -> str:
    labels = {
        "P0": "高优先级关注",
        "P1": "重点观察",
        "P2": "记录观察",
    }
    return labels.get(priority, "观察")


def _lifecycle_label(lifecycle_stage: str) -> str:
    labels = {
        "ignition": "点火",
        "developing": "发酵",
        "divergence": "分歧",
        "returning": "回流",
        "climax": "高潮",
        "fading": "退潮",
        "extinguished": "熄火",
    }
    return labels.get(lifecycle_stage, "待确认")
