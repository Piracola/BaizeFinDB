import argparse
import asyncio
import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.portfolio_models import PortfolioHolding, UserProfile, WatchlistItem
from app.db.radar_models import RadarScanBatch, RadarSignal, RadarSignalReview, SignalEvidence
from app.db.report_models import Report
from app.db.session import AsyncSessionLocal

DEMO_SEED_KEY = "baizefindb_demo_seed_v1"
DEMO_USER_KEY = "default"
DEMO_MARKET = "A_SHARE"
MAINLINE_SIGNAL_KEY = f"{DEMO_SEED_KEY}:mainline:ai_applications"
RISK_SIGNAL_KEY = f"{DEMO_SEED_KEY}:risk:announcement_review"
REPORT_DETAIL_SEED_KEY = f"{DEMO_SEED_KEY}:quick_report"


async def seed_demo_data(
    session: AsyncSession,
    *,
    now: datetime | None = None,
) -> dict[str, Any]:
    seeded_at = now or datetime.now(UTC)
    summary = _empty_summary(seeded_at)

    user = await _get_or_create_user(session, summary)
    await _get_or_create_holding(session, user, summary)
    await _get_or_create_watchlist_item(session, user, summary)

    batch = await _get_or_create_scan_batch(session, seeded_at, summary)
    mainline_signal = await _get_or_create_mainline_signal(session, batch, seeded_at, summary)
    risk_signal = await _get_or_create_risk_signal(session, batch, seeded_at, summary)

    await _get_or_create_mainline_evidences(session, mainline_signal, seeded_at, summary)
    await _get_or_create_risk_evidence(session, risk_signal, seeded_at, summary)
    await _get_or_create_review(
        session,
        signal=mainline_signal,
        review_status="approved",
        reasons=[
            "demo_seed",
            "p1_quick_report_candidate",
            "rule_review_passed",
        ],
        details={
            "seed_key": DEMO_SEED_KEY,
            "review_context": "signal_candidate",
            "m5_review_scope_reasons": ["p1_quick_report_candidate"],
        },
        summary=summary,
    )
    await _get_or_create_review(
        session,
        signal=risk_signal,
        review_status="needs_human_review",
        reasons=[
            "demo_seed",
            "risk_candidate",
            "manual_review_demo_gate",
        ],
        details={
            "seed_key": DEMO_SEED_KEY,
            "review_context": "signal_candidate",
            "m5_review_scope_reasons": ["risk_candidate"],
        },
        summary=summary,
    )
    report = await _get_or_create_report(session, user, mainline_signal, seeded_at, summary)

    await session.commit()

    summary["ids"] = {
        "user": user.id,
        "scan_batch": batch.id,
        "signals": {
            "mainline": mainline_signal.id,
            "risk": risk_signal.id,
        },
        "report": report.id,
    }
    summary["total_created"] = sum(summary["created"].values())
    summary["total_reused"] = sum(summary["reused"].values())
    return summary


def _empty_summary(seeded_at: datetime) -> dict[str, Any]:
    return {
        "seed_key": DEMO_SEED_KEY,
        "seeded_at": seeded_at.isoformat(),
        "status": "ok",
        "created": {},
        "reused": {},
        "ids": {},
    }


def _mark(summary: dict[str, Any], bucket: str, name: str) -> None:
    counts = summary[bucket]
    counts[name] = counts.get(name, 0) + 1


async def _get_or_create_user(
    session: AsyncSession,
    summary: dict[str, Any],
) -> UserProfile:
    user = await session.scalar(select(UserProfile).where(UserProfile.user_key == DEMO_USER_KEY))
    if user is not None:
        _mark(summary, "reused", "users")
        return user

    user = UserProfile(
        user_key=DEMO_USER_KEY,
        display_name="BaizeFinDB Demo User",
        is_active=True,
    )
    session.add(user)
    await session.flush()
    _mark(summary, "created", "users")
    return user


async def _get_or_create_holding(
    session: AsyncSession,
    user: UserProfile,
    summary: dict[str, Any],
) -> PortfolioHolding:
    holding = await session.scalar(
        select(PortfolioHolding).where(
            PortfolioHolding.user_id == user.id,
            PortfolioHolding.market == DEMO_MARKET,
            PortfolioHolding.instrument_code == "DEMO001",
        )
    )
    if holding is not None:
        _mark(summary, "reused", "portfolio_holdings")
        return holding

    holding = PortfolioHolding(
        user_id=user.id,
        instrument_code="DEMO001",
        instrument_name="Demo Theme Basket",
        market=DEMO_MARKET,
        note="Synthetic holding context for first-use workflow validation.",
        cost_price=None,
        position_ratio=None,
        alert_enabled=True,
    )
    session.add(holding)
    await session.flush()
    _mark(summary, "created", "portfolio_holdings")
    return holding


async def _get_or_create_watchlist_item(
    session: AsyncSession,
    user: UserProfile,
    summary: dict[str, Any],
) -> WatchlistItem:
    item = await session.scalar(
        select(WatchlistItem).where(
            WatchlistItem.user_id == user.id,
            WatchlistItem.market == DEMO_MARKET,
            WatchlistItem.instrument_code == "DEMO002",
        )
    )
    if item is not None:
        _mark(summary, "reused", "watchlist_items")
        return item

    item = WatchlistItem(
        user_id=user.id,
        instrument_code="DEMO002",
        instrument_name="Demo Risk Watch",
        market=DEMO_MARKET,
        note="Synthetic watchlist context for radar and report demos.",
        alert_enabled=True,
    )
    session.add(item)
    await session.flush()
    _mark(summary, "created", "watchlist_items")
    return item


async def _get_or_create_scan_batch(
    session: AsyncSession,
    seeded_at: datetime,
    summary: dict[str, Any],
) -> RadarScanBatch:
    signals = await session.scalars(
        select(RadarSignal).where(
            RadarSignal.signal_key.in_([MAINLINE_SIGNAL_KEY, RISK_SIGNAL_KEY])
        )
    )
    existing_signal = next(iter(signals.all()), None)
    if existing_signal is not None:
        batch = await session.get(RadarScanBatch, existing_signal.batch_id)
        if batch is not None:
            _mark(summary, "reused", "radar_scan_batches")
            return batch

    batch = RadarScanBatch(
        status="success",
        started_at=seeded_at - timedelta(minutes=5),
        finished_at=seeded_at - timedelta(minutes=4),
        source_snapshot_ids=[],
        summary={
            "seed_key": DEMO_SEED_KEY,
            "candidate_count": 2,
            "priority_counts": {"P0": 1, "P1": 1, "P2": 0},
            "lifecycle_counts": {"ignition": 1, "developing": 1},
            "market_sentiment": {
                "limit_up_count": 12,
                "limit_down_count": 2,
                "broken_limit_up_count": 3,
                "net_limit_pressure": 7,
                "sentiment_bias": "positive",
            },
        },
        error_message=None,
    )
    session.add(batch)
    await session.flush()
    _mark(summary, "created", "radar_scan_batches")
    return batch


async def _get_or_create_mainline_signal(
    session: AsyncSession,
    batch: RadarScanBatch,
    seeded_at: datetime,
    summary: dict[str, Any],
) -> RadarSignal:
    signal = await _find_signal(session, MAINLINE_SIGNAL_KEY)
    if signal is not None:
        _mark(summary, "reused", "radar_signals")
        return signal

    signal = RadarSignal(
        batch_id=batch.id,
        signal_key=MAINLINE_SIGNAL_KEY,
        subject_type="sector",
        subject_code="DEMO-AI",
        subject_name="AI Applications Demo Theme",
        priority="P1",
        lifecycle_stage="developing",
        review_status="approved",
        title="Demo sector theme shows broad attention",
        summary=(
            "Synthetic sector radar signal for validating first-use research workflows. "
            "Backend priority and lifecycle are fixed by the seeded record."
        ),
        metrics={
            "seed_key": DEMO_SEED_KEY,
            "pct_change": 3.6,
            "breadth": 0.72,
            "rising_count": 18,
            "falling_count": 7,
            "leading_stock": "Demo Leader A",
            "leading_stock_pct_change": 6.8,
            "provider_quality": {"status": "ok", "row_count": 48},
            "continuity": {
                "repeat_count": 3,
                "window_minutes": 30,
                "quick_report_candidate": True,
            },
            "market_sentiment": {
                "sentiment_bias": "positive",
                "net_limit_pressure": 7,
            },
        },
        evidence_count=2,
        created_at=seeded_at - timedelta(minutes=3),
    )
    session.add(signal)
    await session.flush()
    _mark(summary, "created", "radar_signals")
    return signal


async def _get_or_create_risk_signal(
    session: AsyncSession,
    batch: RadarScanBatch,
    seeded_at: datetime,
    summary: dict[str, Any],
) -> RadarSignal:
    signal = await _find_signal(session, RISK_SIGNAL_KEY)
    if signal is not None:
        _mark(summary, "reused", "radar_signals")
        return signal

    signal = RadarSignal(
        batch_id=batch.id,
        signal_key=RISK_SIGNAL_KEY,
        subject_type="risk_event",
        subject_code="DEMO-RISK",
        subject_name="Demo Announcement Review Risk",
        priority="P0",
        lifecycle_stage="ignition",
        review_status="needs_human_review",
        title="Demo announcement risk requires review",
        summary=(
            "Synthetic risk radar signal for validating review gates and warning display. "
            "It is a demo fixture and does not describe a real issuer."
        ),
        metrics={
            "seed_key": DEMO_SEED_KEY,
            "risk_event_type": "announcement_risk",
            "severity": "high",
            "provider_quality": {"status": "ok", "row_count": 1},
            "review_hints": ["synthetic_risk_event", "manual_review_demo_gate"],
        },
        evidence_count=1,
        created_at=seeded_at - timedelta(minutes=2),
    )
    session.add(signal)
    await session.flush()
    _mark(summary, "created", "radar_signals")
    return signal


async def _find_signal(session: AsyncSession, signal_key: str) -> RadarSignal | None:
    return await session.scalar(select(RadarSignal).where(RadarSignal.signal_key == signal_key))


async def _get_or_create_mainline_evidences(
    session: AsyncSession,
    signal: RadarSignal,
    seeded_at: datetime,
    summary: dict[str, Any],
) -> None:
    await _get_or_create_evidence(
        session,
        signal=signal,
        evidence_type="market_snapshot",
        source_ref=f"{DEMO_SEED_KEY}:mainline:breadth",
        source_time=seeded_at - timedelta(minutes=4),
        collected_at=seeded_at - timedelta(minutes=4),
        raw_excerpt="Synthetic demo snapshot: broad constituent participation is present.",
        normalized_summary=(
            "Demo sector breadth is positive with balanced constituent participation."
        ),
        confidence=0.82,
        freshness="fresh",
        details={
            "seed_key": DEMO_SEED_KEY,
            "metrics": {
                "pct_change": 3.6,
                "breadth": 0.72,
                "rising_count": 18,
                "falling_count": 7,
            },
            "provider_quality": {"status": "ok"},
        },
        summary=summary,
    )
    await _get_or_create_evidence(
        session,
        signal=signal,
        evidence_type="market_sentiment",
        source_ref=f"{DEMO_SEED_KEY}:mainline:sentiment",
        source_time=seeded_at - timedelta(minutes=4),
        collected_at=seeded_at - timedelta(minutes=4),
        raw_excerpt="Synthetic demo sentiment: limit-up pressure exceeds downside pressure.",
        normalized_summary=(
            "Demo market sentiment supports attention without changing backend priority."
        ),
        confidence=0.76,
        freshness="fresh",
        details={
            "seed_key": DEMO_SEED_KEY,
            "metrics": {
                "limit_up_count": 12,
                "limit_down_count": 2,
                "broken_limit_up_count": 3,
            },
            "provider_quality": {"status": "ok"},
        },
        summary=summary,
    )


async def _get_or_create_risk_evidence(
    session: AsyncSession,
    signal: RadarSignal,
    seeded_at: datetime,
    summary: dict[str, Any],
) -> None:
    await _get_or_create_evidence(
        session,
        signal=signal,
        evidence_type="announcement_risk",
        source_ref=f"{DEMO_SEED_KEY}:risk:announcement",
        source_time=seeded_at - timedelta(minutes=3),
        collected_at=seeded_at - timedelta(minutes=3),
        raw_excerpt="Synthetic demo announcement excerpt: review marker requires attention.",
        normalized_summary=(
            "Demo announcement risk is flagged for manual research review before publishing."
        ),
        confidence=0.71,
        freshness="fresh",
        details={
            "seed_key": DEMO_SEED_KEY,
            "risk_event_type": "announcement_risk",
            "severity": "high",
            "provider_quality": {"status": "ok"},
        },
        summary=summary,
    )


async def _get_or_create_evidence(
    session: AsyncSession,
    *,
    signal: RadarSignal,
    evidence_type: str,
    source_ref: str,
    source_time: datetime,
    collected_at: datetime,
    raw_excerpt: str,
    normalized_summary: str,
    confidence: float,
    freshness: str,
    details: dict[str, Any],
    summary: dict[str, Any],
) -> SignalEvidence:
    evidence = await session.scalar(
        select(SignalEvidence).where(
            SignalEvidence.signal_id == signal.id,
            SignalEvidence.evidence_type == evidence_type,
            SignalEvidence.source_name == "demo_seed",
            SignalEvidence.source_ref == source_ref,
        )
    )
    if evidence is not None:
        _mark(summary, "reused", "signal_evidences")
        return evidence

    evidence = SignalEvidence(
        signal_id=signal.id,
        evidence_type=evidence_type,
        source_name="demo_seed",
        source_ref=source_ref,
        source_time=source_time,
        collected_at=collected_at,
        raw_excerpt=raw_excerpt,
        normalized_summary=normalized_summary,
        confidence=confidence,
        freshness=freshness,
        details=details,
        public_share_policy="internal_summary_only",
    )
    session.add(evidence)
    await session.flush()
    _mark(summary, "created", "signal_evidences")
    return evidence


async def _get_or_create_review(
    session: AsyncSession,
    *,
    signal: RadarSignal,
    review_status: str,
    reasons: list[str],
    details: dict[str, Any],
    summary: dict[str, Any],
) -> RadarSignalReview:
    review = await session.scalar(
        select(RadarSignalReview).where(
            RadarSignalReview.signal_id == signal.id,
            RadarSignalReview.reviewer == "demo_seed_review",
            RadarSignalReview.rule_version == DEMO_SEED_KEY,
        )
    )
    if review is not None:
        _mark(summary, "reused", "radar_signal_reviews")
        return review

    review = RadarSignalReview(
        signal_id=signal.id,
        review_status=review_status,
        reviewer="demo_seed_review",
        rule_version=DEMO_SEED_KEY,
        reasons=reasons,
        details=details,
    )
    signal.review_status = review_status
    session.add(review)
    await session.flush()
    _mark(summary, "created", "radar_signal_reviews")
    return review


async def _get_or_create_report(
    session: AsyncSession,
    user: UserProfile,
    signal: RadarSignal,
    seeded_at: datetime,
    summary: dict[str, Any],
) -> Report:
    report = await session.scalar(
        select(Report).where(
            Report.user_id == user.id,
            Report.signal_id == signal.id,
            Report.report_type == "quick",
            Report.title == "Quick demo report: AI Applications Demo Theme",
        )
    )
    if report is not None:
        _mark(summary, "reused", "reports")
        summary["ids"]["report"] = report.id
        return report

    report = Report(
        user_id=user.id,
        signal_id=signal.id,
        report_type="quick",
        status="generated",
        title="Quick demo report: AI Applications Demo Theme",
        summary="Synthetic quick report for validating report list and detail flows.",
        body_markdown=(
            "# Quick demo report: AI Applications Demo Theme\n\n"
            "This synthetic report validates BaizeFinDB research workflow screens.\n\n"
            "## Context\n\n"
            "- Backend seeded priority: P1.\n"
            "- Backend seeded lifecycle: developing.\n"
            "- Evidence is synthetic and bounded for demo use.\n\n"
            "## Boundary\n\n"
            "Only use this record to test attention, review, and reporting flows. "
            "It is not real market research and does not provide investment advice."
        ),
        suggestion_label="继续观察",
        review_status="approved",
        details={
            "seed_key": REPORT_DETAIL_SEED_KEY,
            "source_kind": "radar_signal",
            "source_signal_id": signal.id,
            "source_priority": signal.priority,
            "source_lifecycle_stage": signal.lifecycle_stage,
            "generation_mode": "deterministic_seed_fixture",
            "model_status": "not_used",
            "report_depth": "quick",
            "created_for": "development_demo",
        },
        created_at=seeded_at - timedelta(minutes=1),
    )
    session.add(report)
    await session.flush()
    summary["ids"]["report"] = report.id
    _mark(summary, "created", "reports")
    return report


async def _run_cli(args: argparse.Namespace) -> int:
    async with AsyncSessionLocal() as session:
        summary = await seed_demo_data(session)

    output = json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True)
    if args.json_output:
        output_path = Path(args.json_output)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(output + "\n", encoding="utf-8")

    print(output)
    return 0


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Seed safe BaizeFinDB development/demo data into the configured database.",
    )
    parser.add_argument(
        "--json-output",
        help="Optional path for writing the same compact JSON summary printed to stdout.",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    return asyncio.run(_run_cli(parse_args(argv)))


if __name__ == "__main__":
    raise SystemExit(main())
