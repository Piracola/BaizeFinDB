from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.db.base import Base
from app.db.radar_models import RadarScanBatch, RadarSignal, SignalEvidence
from app.db.session import get_db_session
from app.governance.review import review_radar_signal
from app.main import create_app
from app.radar.schemas import RadarReviewStatus


@pytest_asyncio.fixture
async def session_factory() -> AsyncIterator[async_sessionmaker[AsyncSession]]:
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)

    try:
        yield async_sessionmaker(engine, expire_on_commit=False)
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_governance_review_approves_safe_signal(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    async with session_factory() as session:
        signal_id = await _create_signal(session)

        review = await review_radar_signal(session, signal_id)
        signal = await session.get(RadarSignal, signal_id)

    assert review is not None
    assert review.review_status == RadarReviewStatus.APPROVED
    assert "rule_review_passed" in review.reasons
    assert signal is not None
    assert signal.review_status == RadarReviewStatus.APPROVED.value


@pytest.mark.asyncio
async def test_governance_review_blocks_signal_without_evidence(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    async with session_factory() as session:
        signal_id = await _create_signal(session, evidence_count=1, with_evidence=False)

        review = await review_radar_signal(session, signal_id)

    assert review is not None
    assert review.review_status == RadarReviewStatus.BLOCKED
    assert "missing_evidence" in review.reasons


@pytest.mark.asyncio
async def test_governance_review_uses_actual_evidence_when_count_is_stale(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    async with session_factory() as session:
        signal_id = await _create_signal(session, evidence_count=0)

        review = await review_radar_signal(session, signal_id)

    assert review is not None
    assert review.review_status == RadarReviewStatus.NEEDS_HUMAN_REVIEW
    assert "missing_evidence" not in review.reasons
    assert "evidence_count_mismatch" in review.reasons


@pytest.mark.asyncio
async def test_governance_review_blocks_forbidden_trading_language(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    async with session_factory() as session:
        signal_id = await _create_signal(
            session,
            summary="Guardrail fixture with forbidden wording: 保证收益.",
        )

        review = await review_radar_signal(session, signal_id)

    assert review is not None
    assert review.review_status == RadarReviewStatus.BLOCKED
    assert "forbidden_trading_language" in review.reasons
    assert review.details["matched_forbidden_terms"] == ["保证收益"]


@pytest.mark.asyncio
async def test_governance_review_allows_negated_safe_trading_language(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    async with session_factory() as session:
        signal_id = await _create_signal(
            session,
            summary="仅作研究关注，不构成投资建议，不保证收益。",
        )

        review = await review_radar_signal(session, signal_id)

    assert review is not None
    assert review.review_status == RadarReviewStatus.APPROVED
    assert "forbidden_trading_language" not in review.reasons


@pytest.mark.asyncio
async def test_governance_review_blocks_actionable_buy_language_with_safe_disclaimer(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    async with session_factory() as session:
        signal_id = await _create_signal(
            session,
            summary="仅作研究关注，不保证收益，但请马上买入。",
        )

        review = await review_radar_signal(session, signal_id)

    assert review is not None
    assert review.review_status == RadarReviewStatus.BLOCKED
    assert "forbidden_trading_language" in review.reasons
    assert review.details["matched_forbidden_terms"] == ["马上买入"]


@pytest.mark.asyncio
async def test_governance_review_allows_negated_action_warning(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    async with session_factory() as session:
        signal_id = await _create_signal(
            session,
            summary="风险提示：不要马上买入，禁止满仓，不能跟着买。",
        )

        review = await review_radar_signal(session, signal_id)

    assert review is not None
    assert review.review_status == RadarReviewStatus.APPROVED
    assert "forbidden_trading_language" not in review.reasons


@pytest.mark.asyncio
async def test_governance_review_blocks_spaced_forbidden_language(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    async with session_factory() as session:
        signal_id = await _create_signal(
            session,
            summary="Guardrail fixture with spaced wording: 马 上 买 入，保 证 收 益。",
        )

        review = await review_radar_signal(session, signal_id)

    assert review is not None
    assert review.review_status == RadarReviewStatus.BLOCKED
    assert "forbidden_trading_language" in review.reasons
    assert review.details["matched_forbidden_terms"] == ["马上买入", "保证收益"]


@pytest.mark.asyncio
async def test_governance_review_blocks_common_hype_language(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    async with session_factory() as session:
        signal_id = await _create_signal(
            session,
            summary="Guardrail fixture with hype wording: 闭眼冲，翻倍票，抄底加仓。",
        )

        review = await review_radar_signal(session, signal_id)

    assert review is not None
    assert review.review_status == RadarReviewStatus.BLOCKED
    assert "forbidden_trading_language" in review.reasons
    assert review.details["matched_forbidden_terms"] == [
        "闭眼冲",
        "翻倍票",
        "抄底加仓",
    ]


@pytest.mark.asyncio
async def test_governance_review_marks_low_confidence_for_human_review(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    async with session_factory() as session:
        signal_id = await _create_signal(session, confidence=0.2)

        review = await review_radar_signal(session, signal_id)

    assert review is not None
    assert review.review_status == RadarReviewStatus.NEEDS_HUMAN_REVIEW
    assert "low_evidence_confidence" in review.reasons


@pytest.mark.asyncio
async def test_governance_review_marks_degraded_provider_quality_for_human_review(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    async with session_factory() as session:
        signal_id = await _create_signal(session, provider_quality_status="degraded")

        review = await review_radar_signal(session, signal_id)

    assert review is not None
    assert review.review_status == RadarReviewStatus.NEEDS_HUMAN_REVIEW
    assert "provider_quality_needs_review" in review.reasons
    assert review.details["provider_quality_statuses"] == ["degraded"]


@pytest.mark.asyncio
async def test_governance_review_marks_evidence_conflict_for_human_review(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    async with session_factory() as session:
        signal_id = await _create_signal(
            session,
            metrics_extra={"pct_change": 3.4, "breadth": 0.7},
            evidence_details_extra={
                "metrics": {"pct_change": -1.2, "breadth": 0.7}
            },
        )

        review = await review_radar_signal(session, signal_id)

    assert review is not None
    assert review.review_status == RadarReviewStatus.NEEDS_HUMAN_REVIEW
    assert "evidence_conflict" in review.reasons
    assert review.details["evidence_conflicts"][0]["field"] == "pct_change"


@pytest.mark.asyncio
async def test_governance_review_marks_duplicate_trigger_review_hints_for_human_review(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    async with session_factory() as session:
        signal_id = await _create_signal(
            session,
            metrics_extra={
                "review_hints": [
                    "continuous_p1_trigger",
                    "continuous_p1_trigger",
                ]
            },
        )

        review = await review_radar_signal(session, signal_id)

    assert review is not None
    assert review.review_status == RadarReviewStatus.NEEDS_HUMAN_REVIEW
    assert "duplicate_trigger_review_hints" in review.reasons
    assert review.details["duplicate_trigger_review_hints"][0]["count"] == 2


@pytest.mark.asyncio
async def test_governance_review_marks_stale_source_for_human_review(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    collected_at = datetime.now(UTC)

    async with session_factory() as session:
        signal_id = await _create_signal(
            session,
            evidence_source_time=collected_at - timedelta(days=5),
            evidence_collected_at=collected_at,
        )

        review = await review_radar_signal(session, signal_id)

    assert review is not None
    assert review.review_status == RadarReviewStatus.NEEDS_HUMAN_REVIEW
    assert "stale_source" in review.reasons
    assert review.details["stale_sources"][0]["source_age_hours"] == 120.0


@pytest.mark.asyncio
async def test_governance_review_blocks_failed_provider_quality(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    async with session_factory() as session:
        signal_id = await _create_signal(session, provider_quality_status="failed")

        review = await review_radar_signal(session, signal_id)

    assert review is not None
    assert review.review_status == RadarReviewStatus.BLOCKED
    assert "failed_provider_quality" in review.reasons


@pytest.mark.asyncio
async def test_radar_review_api_posts_and_lists_reviews(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    async with session_factory() as session:
        signal_id = await _create_signal(
            session,
            priority="P0",
            quick_report_candidate=True,
        )

    app = create_app()

    async def override_db_session() -> AsyncIterator[AsyncSession]:
        async with session_factory() as session:
            yield session

    app.dependency_overrides[get_db_session] = override_db_session

    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            review_response = await client.post(f"/radar/signals/{signal_id}/review")
            reviews_response = await client.get(f"/radar/signals/{signal_id}/reviews")
            detail_response = await client.get(f"/radar/signals/{signal_id}")
            missing_response = await client.post("/radar/signals/999999/review")
            missing_reviews_response = await client.get("/radar/signals/999999/reviews")
    finally:
        app.dependency_overrides.clear()

    assert review_response.status_code == 200
    assert review_response.json()["review_status"] == "approved"
    assert "high_priority_review" in review_response.json()["reasons"]
    assert "quick_report_review" in review_response.json()["reasons"]

    assert reviews_response.status_code == 200
    assert len(reviews_response.json()) == 1
    assert reviews_response.json()[0]["id"] == review_response.json()["id"]

    assert detail_response.status_code == 200
    assert detail_response.json()["review_status"] == "approved"

    assert missing_response.status_code == 404
    assert missing_reviews_response.status_code == 404


@pytest.mark.asyncio
async def test_radar_review_api_blocks_signal_without_evidence(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    async with session_factory() as session:
        signal_id = await _create_signal(session, evidence_count=1, with_evidence=False)

    app = create_app()

    async def override_db_session() -> AsyncIterator[AsyncSession]:
        async with session_factory() as session:
            yield session

    app.dependency_overrides[get_db_session] = override_db_session

    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            review_response = await client.post(f"/radar/signals/{signal_id}/review")
            detail_response = await client.get(f"/radar/signals/{signal_id}")
    finally:
        app.dependency_overrides.clear()

    assert review_response.status_code == 200
    assert review_response.json()["review_status"] == "blocked"
    assert "missing_evidence" in review_response.json()["reasons"]
    assert review_response.json()["details"]["actual_evidence_count"] == 0

    assert detail_response.status_code == 200
    assert detail_response.json()["review_status"] == "blocked"


@pytest.mark.asyncio
async def test_radar_review_api_marks_low_confidence_for_human_review(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    async with session_factory() as session:
        signal_id = await _create_signal(session, confidence=0.2)

    app = create_app()

    async def override_db_session() -> AsyncIterator[AsyncSession]:
        async with session_factory() as session:
            yield session

    app.dependency_overrides[get_db_session] = override_db_session

    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            review_response = await client.post(f"/radar/signals/{signal_id}/review")
            detail_response = await client.get(f"/radar/signals/{signal_id}")
    finally:
        app.dependency_overrides.clear()

    assert review_response.status_code == 200
    assert review_response.json()["review_status"] == "needs_human_review"
    assert "low_evidence_confidence" in review_response.json()["reasons"]
    assert review_response.json()["details"]["min_evidence_confidence"] == 0.2

    assert detail_response.status_code == 200
    assert detail_response.json()["review_status"] == "needs_human_review"


@pytest.mark.asyncio
async def test_radar_review_api_lists_review_history_latest_first(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    async with session_factory() as session:
        signal_id = await _create_signal(session)

    app = create_app()

    async def override_db_session() -> AsyncIterator[AsyncSession]:
        async with session_factory() as session:
            yield session

    app.dependency_overrides[get_db_session] = override_db_session

    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            first_review_response = await client.post(f"/radar/signals/{signal_id}/review")
            second_review_response = await client.post(f"/radar/signals/{signal_id}/review")
            third_review_response = await client.post(f"/radar/signals/{signal_id}/review")
            reviews_response = await client.get(f"/radar/signals/{signal_id}/reviews")
    finally:
        app.dependency_overrides.clear()

    assert first_review_response.status_code == 200
    assert second_review_response.status_code == 200
    assert third_review_response.status_code == 200
    assert reviews_response.status_code == 200

    expected_ids = [
        third_review_response.json()["id"],
        second_review_response.json()["id"],
        first_review_response.json()["id"],
    ]
    assert [review["id"] for review in reviews_response.json()] == expected_ids
    assert [review["review_status"] for review in reviews_response.json()] == [
        "approved",
        "approved",
        "approved",
    ]


async def _create_signal(
    session: AsyncSession,
    *,
    priority: str = "P1",
    summary: str = "Research attention signal from provider data, without trading advice.",
    confidence: float = 0.9,
    evidence_count: int = 1,
    with_evidence: bool = True,
    quick_report_candidate: bool = False,
    provider_quality_status: str | None = None,
    metrics_extra: dict[str, object] | None = None,
    evidence_details_extra: dict[str, object] | None = None,
    evidence_source_time: datetime | None = None,
    evidence_collected_at: datetime | None = None,
    evidence_freshness: str = "snapshot_latest",
) -> int:
    now = datetime.now(UTC)
    metrics: dict[str, object] = {
        "continuity": {"quick_report_candidate": quick_report_candidate}
    }
    evidence_details: dict[str, object] = {"source": "test"}

    if provider_quality_status is not None:
        provider_quality = {
            "status": provider_quality_status,
            "confidence": 0.4 if provider_quality_status != "ok" else 0.95,
            "freshness": "test",
            "missing_fields": ["pct_change"] if provider_quality_status == "degraded" else [],
        }
        metrics["provider_quality"] = provider_quality
        evidence_details["provider_quality"] = provider_quality

    if metrics_extra is not None:
        metrics.update(metrics_extra)

    if evidence_details_extra is not None:
        evidence_details.update(evidence_details_extra)

    batch = RadarScanBatch(
        status="success",
        started_at=now,
        finished_at=now,
        source_snapshot_ids=[],
        summary={},
    )
    session.add(batch)
    await session.flush()

    signal = RadarSignal(
        batch_id=batch.id,
        signal_key=f"test:signal:{now.timestamp()}",
        subject_type="sector_concept",
        subject_code="GN001",
        subject_name="AI Applications",
        priority=priority,
        lifecycle_stage="developing",
        review_status=RadarReviewStatus.CANDIDATE.value,
        title="P1 radar candidate: AI Applications",
        summary=summary,
        metrics=metrics,
        evidence_count=evidence_count,
    )
    session.add(signal)
    await session.flush()

    if with_evidence:
        session.add(
            SignalEvidence(
                signal_id=signal.id,
                evidence_type="market_snapshot",
                source_name="akshare",
                source_ref="market_snapshot:1",
                source_time=evidence_source_time,
                collected_at=evidence_collected_at or now,
                raw_excerpt="AI Applications: pct_change=3.4, breadth=0.7",
                normalized_summary="Provider snapshot shows sector movement.",
                confidence=confidence,
                freshness=evidence_freshness,
                details=evidence_details,
                public_share_policy="internal_summary_only",
            )
        )

    await session.commit()
    return signal.id
