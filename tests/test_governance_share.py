from collections.abc import AsyncIterator
from datetime import UTC, datetime

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.db.base import Base
from app.db.radar_models import RadarScanBatch, RadarSignal, SignalEvidence
from app.db.session import get_db_session
from app.governance.review import review_radar_signal
from app.governance.share import get_radar_signal_share_preview
from app.main import create_app
from app.radar.schemas import RadarReviewStatus, RadarSignalShareStatus


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
async def test_share_preview_blocks_unreviewed_signal_and_hides_raw_source_data(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    async with session_factory() as session:
        signal_id = await _create_signal(
            session,
            raw_excerpt="Raw source says visit https://example.com/a/b for the full text.",
            source_ref="https://example.com/a/b",
            source_name="example.com",
            details={"source_url": "https://example.com/a/b", "personal_note": "private"},
        )

        preview = await get_radar_signal_share_preview(session, signal_id)

    assert preview is not None
    assert preview.share_status == RadarSignalShareStatus.BLOCKED
    assert preview.blocked_reasons == ["review_required", "signal_review_not_approved"]
    assert "raw_text_omitted" in preview.sanitization_notes

    serialized = preview.model_dump_json()
    assert "https://example.com" not in serialized
    assert "source_url" not in serialized
    assert "personal_note" not in serialized
    assert "Raw source says" not in serialized
    assert "example.com" not in serialized


@pytest.mark.asyncio
async def test_share_preview_redacts_source_locators_from_visible_text(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    async with session_factory() as session:
        signal_id = await _create_signal(
            session,
            title="P1 radar candidate from tushare.pro",
            summary="Read more at https://example.com/a/b and akshare.akfamily.xyz.",
            normalized_summary="Provider summary mirrored from market.example.hk.",
        )
        await review_radar_signal(session, signal_id)

        preview = await get_radar_signal_share_preview(session, signal_id)

    assert preview is not None
    assert preview.share_status == RadarSignalShareStatus.READY
    assert "source_locator_redacted" in preview.sanitization_notes
    serialized = preview.model_dump_json()
    assert "example.com" not in serialized
    assert "https://example.com" not in serialized
    assert "tushare.pro" not in serialized
    assert "akshare.akfamily.xyz" not in serialized
    assert "market.example.hk" not in serialized


@pytest.mark.asyncio
async def test_share_preview_notes_redaction_from_title_only(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    async with session_factory() as session:
        signal_id = await _create_signal(
            session,
            title="P1 radar candidate from source.example.ai",
        )
        await review_radar_signal(session, signal_id)

        preview = await get_radar_signal_share_preview(session, signal_id)

    assert preview is not None
    assert "source_locator_redacted" in preview.sanitization_notes
    assert "source.example.ai" not in preview.model_dump_json()


@pytest.mark.asyncio
async def test_share_preview_is_ready_after_approved_review(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    async with session_factory() as session:
        signal_id = await _create_signal(session)
        review = await review_radar_signal(session, signal_id)

        preview = await get_radar_signal_share_preview(session, signal_id)

    assert review is not None
    assert review.review_status == RadarReviewStatus.APPROVED
    assert preview is not None
    assert preview.share_status == RadarSignalShareStatus.READY
    assert preview.latest_review_id == review.id
    assert preview.blocked_reasons == []
    assert preview.evidences[0].summary == "Provider snapshot shows sector movement."
    assert preview.evidences[0].evidence_label == "市场快照"
    assert preview.evidences[0].confidence_label == "高"
    assert preview.evidences[0].freshness_label == "较新"


@pytest.mark.asyncio
async def test_share_preview_blocks_unsafe_public_share_policy(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    async with session_factory() as session:
        signal_id = await _create_signal(session, public_share_policy="internal_only")
        await review_radar_signal(session, signal_id)

        preview = await get_radar_signal_share_preview(session, signal_id)

    assert preview is not None
    assert preview.share_status == RadarSignalShareStatus.BLOCKED
    assert "unsafe_public_share_policy" in preview.blocked_reasons


@pytest.mark.asyncio
async def test_share_preview_api_returns_sanitized_payload(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    async with session_factory() as session:
        signal_id = await _create_signal(session)
        await review_radar_signal(session, signal_id)

    app = create_app()

    async def override_db_session() -> AsyncIterator[AsyncSession]:
        async with session_factory() as session:
            yield session

    app.dependency_overrides[get_db_session] = override_db_session

    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get(f"/radar/signals/{signal_id}/share-preview")
            payload_response = await client.get(f"/radar/signals/{signal_id}/share-payload")
            missing_response = await client.get("/radar/signals/999999/share-preview")
            missing_payload_response = await client.get(
                "/radar/signals/999999/share-payload"
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json()["share_status"] == "ready"
    assert response.json()["disclaimer"] == (
        "仅供个人研究和复盘，不构成投资建议，不保证收益，用户需要自行决策并承担风险。"
    )
    assert "raw_excerpt" not in response.text
    assert "market_snapshot:1" not in response.text
    assert "market_snapshot" not in response.text
    assert "snapshot_latest" not in response.text
    assert "source_time" not in response.text
    assert '"confidence":' not in response.text
    assert '"source":"test"' not in response.text

    assert payload_response.status_code == 200
    assert payload_response.json()["priority_label"] == "重点观察"
    assert payload_response.json()["lifecycle_label"] == "发酵"
    assert payload_response.json()["disclaimer"] == response.json()["disclaimer"]
    assert "signal_id" not in payload_response.text
    assert "review_status" not in payload_response.text
    assert "latest_review_id" not in payload_response.text
    assert "blocked_reasons" not in payload_response.text
    assert "sanitization_notes" not in payload_response.text
    assert "market_snapshot" not in payload_response.text
    assert "source_time" not in payload_response.text

    assert missing_response.status_code == 404
    assert missing_payload_response.status_code == 404


@pytest.mark.asyncio
async def test_public_share_payload_blocks_unshareable_signal_without_internal_reasons(
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
            payload_response = await client.get(f"/radar/signals/{signal_id}/share-payload")
    finally:
        app.dependency_overrides.clear()

    assert payload_response.status_code == 409
    assert "review_required" not in payload_response.text
    assert "signal_review_not_approved" not in payload_response.text


async def _create_signal(
    session: AsyncSession,
    *,
    title: str = "P1 radar candidate: AI Applications",
    summary: str = "Research attention signal from provider data, without trading advice.",
    raw_excerpt: str = "AI Applications: pct_change=3.4, breadth=0.7",
    normalized_summary: str = "Provider snapshot shows sector movement.",
    source_ref: str = "market_snapshot:1",
    source_name: str = "akshare",
    details: dict[str, object] | None = None,
    public_share_policy: str = "internal_summary_only",
) -> int:
    now = datetime.now(UTC)
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
        signal_key=f"share:test:{now.timestamp()}",
        subject_type="sector_concept",
        subject_code="GN001",
        subject_name="AI Applications",
        priority="P1",
        lifecycle_stage="developing",
        review_status=RadarReviewStatus.CANDIDATE.value,
        title=title,
        summary=summary,
        metrics={"continuity": {"quick_report_candidate": False}},
        evidence_count=1,
    )
    session.add(signal)
    await session.flush()

    session.add(
        SignalEvidence(
            signal_id=signal.id,
            evidence_type="market_snapshot",
            source_name=source_name,
            source_ref=source_ref,
            source_time=None,
            collected_at=now,
            raw_excerpt=raw_excerpt,
            normalized_summary=normalized_summary,
            confidence=0.9,
            freshness="snapshot_latest",
            details=details or {"source": "test"},
            public_share_policy=public_share_policy,
        )
    )

    await session.commit()
    return signal.id
