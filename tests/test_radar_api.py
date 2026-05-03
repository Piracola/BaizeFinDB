from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.db.base import Base
from app.db.provider_models import MarketSnapshot
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


@pytest.mark.asyncio
async def test_radar_api_runs_scan_and_reads_signals(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    async with session_factory() as session:
        session.add(
            MarketSnapshot(
                provider_name="akshare",
                endpoint="stock_board_concept_name_em",
                market="A_SHARE",
                snapshot_type="sector_concept",
                source_time=None,
                collected_at=datetime.now(UTC),
                row_count=1,
                raw_summary={"columns": []},
                normalized_rows=[
                    {
                        "sector_code": "GN001",
                        "sector_name": "AI Applications",
                        "pct_change": 3.4,
                        "turnover_rate": 3.1,
                        "rising_count": 18,
                        "falling_count": 8,
                        "leading_stock": "Example AI",
                        "leading_stock_pct_change": 7.5,
                    }
                ],
                normalization_version="test",
            )
        )
        await session.commit()

    app = create_app()

    async def override_db_session() -> AsyncIterator[AsyncSession]:
        async with session_factory() as session:
            yield session

    app.dependency_overrides[get_db_session] = override_db_session

    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            run_response = await client.post("/radar/scans/run")
            latest_response = await client.get("/radar/scans/latest")
            scan_id = run_response.json()["id"]
            scan_detail_response = await client.get(f"/radar/scans/{scan_id}")
            overview_response = await client.get("/radar/overview")
            signals_response = await client.get("/radar/signals", params={"priority": "P1"})
            signal_id = signals_response.json()[0]["id"]
            detail_response = await client.get(f"/radar/signals/{signal_id}")
            missing_scan_response = await client.get("/radar/scans/999999")
            missing_response = await client.get("/radar/signals/999999")
    finally:
        app.dependency_overrides.clear()

    assert run_response.status_code == 200
    assert run_response.json()["status"] == "success"
    assert run_response.json()["signals"][0]["priority"] == "P1"

    assert latest_response.status_code == 200
    assert latest_response.json()["summary"]["candidate_count"] == 1

    assert scan_detail_response.status_code == 200
    assert scan_detail_response.json()["id"] == run_response.json()["id"]

    assert overview_response.status_code == 200
    overview_payload = overview_response.json()
    assert overview_payload["latest_scan"]["id"] == run_response.json()["id"]
    assert overview_payload["priority_counts"] == {"P0": 0, "P1": 1, "P2": 0}
    assert overview_payload["lifecycle_counts"]["ignition"] == 1
    assert overview_payload["subject_count"] == 1
    assert overview_payload["current_subjects"][0]["subject_name"] == "AI Applications"
    backtrace = overview_payload["stock_backtrace_evidences"][0]
    assert backtrace["stock_name"] == "Example AI"
    assert backtrace["subject_name"] == "AI Applications"

    assert signals_response.status_code == 200
    assert signals_response.json()[0]["subject_name"] == "AI Applications"

    assert detail_response.status_code == 200
    assert detail_response.json()["evidences"][0]["evidence_type"] == "market_snapshot"

    assert missing_scan_response.status_code == 404
    assert missing_response.status_code == 404


@pytest.mark.asyncio
async def test_radar_signals_api_can_include_expired_p2(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    now = datetime.now(UTC)

    async with session_factory() as session:
        scan = RadarScanBatch(
            status="success",
            started_at=now,
            finished_at=now,
            source_snapshot_ids=[],
            summary={"priority_counts": {"P0": 0, "P1": 0, "P2": 2}},
        )
        session.add(scan)
        await session.flush()
        session.add_all(
            [
                _signal(
                    batch_id=scan.id,
                    signal_key="test:p2:api-expired",
                    subject_name="Expired P2 Theme",
                    created_at=now - timedelta(days=8),
                ),
                _signal(
                    batch_id=scan.id,
                    signal_key="test:p2:api-recent",
                    subject_name="Recent P2 Theme",
                    created_at=now - timedelta(days=1),
                ),
            ]
        )
        await session.commit()

    app = create_app()

    async def override_db_session() -> AsyncIterator[AsyncSession]:
        async with session_factory() as session:
            yield session

    app.dependency_overrides[get_db_session] = override_db_session

    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            default_response = await client.get(
                "/radar/signals",
                params={"priority": "P2"},
            )
            historical_response = await client.get(
                "/radar/signals",
                params={"priority": "P2", "include_expired_p2": True},
            )
    finally:
        app.dependency_overrides.clear()

    assert default_response.status_code == 200
    assert [signal["subject_name"] for signal in default_response.json()] == [
        "Recent P2 Theme"
    ]

    assert historical_response.status_code == 200
    assert {signal["subject_name"] for signal in historical_response.json()} == {
        "Expired P2 Theme",
        "Recent P2 Theme",
    }


def _signal(
    *,
    batch_id: int,
    signal_key: str,
    subject_name: str,
    created_at: datetime,
) -> RadarSignal:
    return RadarSignal(
        batch_id=batch_id,
        signal_key=signal_key,
        subject_type="sector_concept",
        subject_code=None,
        subject_name=subject_name,
        priority="P2",
        lifecycle_stage="developing",
        review_status="candidate",
        title=f"P2 radar candidate: {subject_name}",
        summary="Manual signal for API retention tests.",
        metrics={"pct_change": 1.2},
        evidence_count=0,
        created_at=created_at,
    )
