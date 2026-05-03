from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.db.base import Base
from app.db.radar_models import RadarScanBatch, RadarSignal
from app.db.session import get_db_session
from app.main import create_app
from app.scores.service import generate_signal_scores


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


@pytest_asyncio.fixture
async def client(
    session_factory: async_sessionmaker[AsyncSession],
) -> AsyncIterator[AsyncClient]:
    app = create_app()

    async def override_db_session() -> AsyncIterator[AsyncSession]:
        async with session_factory() as session:
            yield session

    app.dependency_overrides[get_db_session] = override_db_session

    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as test_client:
            yield test_client
    finally:
        app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_score_api_generates_four_window_composite_scores(
    session_factory: async_sessionmaker[AsyncSession],
    client: AsyncClient,
) -> None:
    signal_id = await _seed_signal(session_factory)

    response = await client.post(f"/scores/signals/{signal_id}")
    duplicate_response = await client.post(f"/scores/signals/{signal_id}")
    list_response = await client.get(f"/scores/signals/{signal_id}")

    assert response.status_code == 200
    payload = response.json()
    assert payload["signal_id"] == signal_id
    assert [record["window_days"] for record in payload["records"]] == [1, 3, 5, 10]
    assert payload["records"][0]["score_status"] == "generated"
    assert payload["records"][1]["score_status"] == "pending_window"
    assert payload["records"][0]["composite_score"] > 70
    assert payload["records"][0]["components"]["priority"] == 85
    assert payload["records"][0]["components"]["data_quality"] > 80
    assert payload["records"][0]["details"]["scoring_version"] == "m5_composite_v2"
    assert (
        payload["records"][0]["details"]["method"]
        == "calibrated_composite_without_price_only_backtest"
    )
    assert payload["records"][0]["details"]["score_band"] == "strong_attention"
    assert "data_quality" in payload["records"][0]["details"]["weights"]

    assert duplicate_response.status_code == 200
    assert [record["id"] for record in duplicate_response.json()["records"]] == [
        record["id"] for record in payload["records"]
    ]

    assert list_response.status_code == 200
    assert len(list_response.json()["records"]) == 4


@pytest.mark.asyncio
async def test_score_api_returns_404_for_missing_signal(client: AsyncClient) -> None:
    response = await client.post("/scores/signals/999999")

    assert response.status_code == 404


@pytest.mark.asyncio
async def test_score_calibration_uses_data_quality_and_timeliness(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    now = datetime(2026, 1, 10, tzinfo=UTC)
    fresh_signal_id = await _seed_signal(
        session_factory,
        created_at=now - timedelta(hours=1),
        provider_quality={"status": "ok", "confidence": 0.95, "missing_fields": []},
    )
    weak_signal_id = await _seed_signal(
        session_factory,
        priority="P2",
        lifecycle_stage="fading",
        review_status="needs_human_review",
        evidence_count=0,
        created_at=now - timedelta(days=12),
        provider_quality={
            "status": "failed",
            "confidence": 0.0,
            "missing_fields": ["pct_change", "rising_count"],
        },
        continuity={
            "previous_signal_id": None,
            "consecutive_p1_count": 0,
            "quick_report_candidate": False,
        },
    )

    async with session_factory() as session:
        fresh_scores = await generate_signal_scores(session, fresh_signal_id, now=now)
        weak_scores = await generate_signal_scores(session, weak_signal_id, now=now)

    assert fresh_scores is not None
    assert weak_scores is not None

    fresh_record = fresh_scores.records[0]
    weak_record = weak_scores.records[0]

    assert fresh_record.components["data_quality"] > weak_record.components["data_quality"]
    assert fresh_record.components["timeliness"] > weak_record.components["timeliness"]
    assert fresh_record.composite_score > weak_record.composite_score
    assert fresh_record.details["calibration_inputs"]["provider_quality_status"] == "ok"
    assert weak_record.details["calibration_inputs"]["provider_quality_status"] == "failed"
    assert weak_record.details["score_band"] == "low_signal_quality"


async def _seed_signal(
    session_factory: async_sessionmaker[AsyncSession],
    *,
    priority: str = "P0",
    lifecycle_stage: str = "developing",
    review_status: str = "approved",
    evidence_count: int = 2,
    created_at: datetime | None = None,
    provider_quality: dict[str, object] | None = None,
    continuity: dict[str, object] | None = None,
) -> int:
    now = datetime.now(UTC)
    signal_created_at = created_at or now - timedelta(days=2)
    quality = provider_quality or {"status": "ok", "confidence": 0.95, "missing_fields": []}
    continuity_metrics = continuity or {
        "previous_signal_id": 1,
        "consecutive_p1_count": 3,
        "quick_report_candidate": True,
    }
    async with session_factory() as session:
        scan = RadarScanBatch(
            status="success",
            started_at=now,
            finished_at=now,
            source_snapshot_ids=[],
            summary={"priority_counts": {"P0": 1, "P1": 0, "P2": 0}},
        )
        session.add(scan)
        await session.flush()

        signal = RadarSignal(
            batch_id=scan.id,
            signal_key=f"akshare:test:score:{signal_created_at.timestamp()}:{priority}",
            subject_type="sector_concept",
            subject_code="GN001",
            subject_name="AI Applications",
            priority=priority,
            lifecycle_stage=lifecycle_stage,
            review_status=review_status,
            title=f"{priority} radar candidate",
            summary="Composite score seed.",
            metrics={
                "continuity": continuity_metrics,
                "provider_quality": quality,
            },
            evidence_count=evidence_count,
            created_at=signal_created_at,
        )
        session.add(signal)
        await session.commit()
        return signal.id
