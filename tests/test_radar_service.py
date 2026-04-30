from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta

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


@pytest.mark.asyncio
async def test_radar_scan_marks_consecutive_p1_quick_report_candidate(
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
                        "pct_change": 3.2,
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

        await run_radar_scan(session)
        await run_radar_scan(session)
        scan = await run_radar_scan(session)

    assert scan.summary["quick_report_candidate_count"] == 1
    assert scan.signals[0].priority == RadarPriority.P1
    continuity = scan.signals[0].metrics["continuity"]
    assert continuity["consecutive_p1_count"] == 3
    assert continuity["quick_report_candidate"] is True
    assert "continuous_p1_trigger" in continuity["continuity_reasons"]


@pytest.mark.asyncio
async def test_radar_scan_adjusts_lifecycle_from_previous_signal(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    first_collected_at = datetime.now(UTC)

    async with session_factory() as session:
        session.add(
            MarketSnapshot(
                provider_name="akshare",
                endpoint="stock_board_industry_name_em",
                market="A_SHARE",
                snapshot_type="sector_industry",
                source_time=None,
                collected_at=first_collected_at,
                row_count=1,
                raw_summary={"columns": []},
                normalized_rows=[
                    {
                        "sector_code": "BK100",
                        "sector_name": "Advanced Manufacturing",
                        "pct_change": 6.8,
                        "turnover_rate": 4.6,
                        "rising_count": 30,
                        "falling_count": 4,
                        "leading_stock": "Example Robot",
                        "leading_stock_pct_change": 10.5,
                    }
                ],
                normalization_version="test",
            )
        )
        await session.commit()
        first_scan = await run_radar_scan(session)

        session.add(
            MarketSnapshot(
                provider_name="akshare",
                endpoint="stock_board_industry_name_em",
                market="A_SHARE",
                snapshot_type="sector_industry",
                source_time=None,
                collected_at=first_collected_at + timedelta(minutes=5),
                row_count=1,
                raw_summary={"columns": []},
                normalized_rows=[
                    {
                        "sector_code": "BK100",
                        "sector_name": "Advanced Manufacturing",
                        "pct_change": 3.2,
                        "turnover_rate": 3.0,
                        "rising_count": 12,
                        "falling_count": 8,
                        "leading_stock": "Example Robot",
                        "leading_stock_pct_change": 4.5,
                    }
                ],
                normalization_version="test",
            )
        )
        await session.commit()
        second_scan = await run_radar_scan(session)

    assert first_scan.signals[0].lifecycle_stage == "climax"
    assert second_scan.signals[0].lifecycle_stage == "divergence"
    continuity = second_scan.signals[0].metrics["continuity"]
    assert continuity["previous_lifecycle_stage"] == "climax"
    assert continuity["lifecycle_transition"] == "climax_to_divergence"
    assert continuity["pct_change_delta"] < 0
