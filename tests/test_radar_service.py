from collections.abc import AsyncIterator
from datetime import UTC, datetime

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.db.base import Base
from app.db.provider_models import MarketSnapshot
from app.radar.schemas import RadarPriority, RadarScanStatus
from app.radar.service import (
    get_radar_signal_detail,
    list_radar_signals,
    run_radar_scan,
)


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
async def test_radar_scan_generates_signals_from_latest_snapshots(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    async with session_factory() as session:
        session.add(
            MarketSnapshot(
                provider_name="akshare",
                endpoint="stock_board_industry_name_em",
                market="A_SHARE",
                snapshot_type="sector_industry",
                source_time=None,
                collected_at=datetime.now(UTC),
                row_count=2,
                raw_summary={"columns": []},
                normalized_rows=[
                    {
                        "sector_code": "BK001",
                        "sector_name": "Semiconductors",
                        "pct_change": 6.2,
                        "turnover_rate": 4.8,
                        "rising_count": 24,
                        "falling_count": 4,
                        "leading_stock": "Example Tech",
                        "leading_stock_pct_change": 10.0,
                    },
                    {
                        "sector_code": "BK002",
                        "sector_name": "Quiet Sector",
                        "pct_change": 0.2,
                        "rising_count": 3,
                        "falling_count": 20,
                    },
                ],
                normalization_version="test",
            )
        )
        await session.commit()

        scan = await run_radar_scan(session)
        p0_signals = await list_radar_signals(session, priority=RadarPriority.P0)
        detail = await get_radar_signal_detail(session, p0_signals[0].id)

    assert scan.status == RadarScanStatus.SUCCESS
    assert scan.summary["candidate_count"] == 1
    assert scan.summary["priority_counts"]["P0"] == 1
    assert len(scan.signals) == 1
    assert scan.signals[0].subject_name == "Semiconductors"
    assert p0_signals[0].priority == RadarPriority.P0
    assert detail is not None
    assert detail.evidences[0].evidence_type == "market_snapshot"
    assert detail.evidences[0].public_share_policy == "internal_summary_only"


@pytest.mark.asyncio
async def test_radar_scan_records_no_data_without_snapshots(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    async with session_factory() as session:
        scan = await run_radar_scan(session)

    assert scan.status == RadarScanStatus.NO_DATA
    assert scan.summary["candidate_count"] == 0
    assert scan.signals == []
