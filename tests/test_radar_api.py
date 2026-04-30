from collections.abc import AsyncIterator
from datetime import UTC, datetime

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.db.base import Base
from app.db.provider_models import MarketSnapshot
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
            signals_response = await client.get("/radar/signals", params={"priority": "P1"})
            signal_id = signals_response.json()[0]["id"]
            detail_response = await client.get(f"/radar/signals/{signal_id}")
            missing_response = await client.get("/radar/signals/999999")
    finally:
        app.dependency_overrides.clear()

    assert run_response.status_code == 200
    assert run_response.json()["status"] == "success"
    assert run_response.json()["signals"][0]["priority"] == "P1"

    assert latest_response.status_code == 200
    assert latest_response.json()["summary"]["candidate_count"] == 1

    assert signals_response.status_code == 200
    assert signals_response.json()[0]["subject_name"] == "AI Applications"

    assert detail_response.status_code == 200
    assert detail_response.json()["evidences"][0]["evidence_type"] == "market_snapshot"

    assert missing_response.status_code == 404
