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
    assert payload["records"][0]["details"]["scoring_version"] == "m5_composite_v1"
    assert payload["records"][0]["details"]["method"] == "composite_without_price_only_backtest"

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


async def _seed_signal(session_factory: async_sessionmaker[AsyncSession]) -> int:
    now = datetime.now(UTC)
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
            signal_key="akshare:test:score",
            subject_type="sector_concept",
            subject_code="GN001",
            subject_name="AI Applications",
            priority="P0",
            lifecycle_stage="developing",
            review_status="approved",
            title="P0 radar candidate",
            summary="Composite score seed.",
            metrics={
                "continuity": {
                    "previous_signal_id": 1,
                    "consecutive_p1_count": 3,
                    "quick_report_candidate": True,
                },
            },
            evidence_count=2,
            created_at=now - timedelta(days=2),
        )
        session.add(signal)
        await session.commit()
        return signal.id
