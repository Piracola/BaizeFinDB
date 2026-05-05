import importlib.util
import sys
from collections.abc import AsyncIterator
from datetime import UTC, datetime
from pathlib import Path

import pytest
import pytest_asyncio
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.db.base import Base
from app.db.portfolio_models import PortfolioHolding, UserProfile, WatchlistItem
from app.db.radar_models import RadarScanBatch, RadarSignal, RadarSignalReview, SignalEvidence
from app.db.report_models import Report
from app.radar.service import get_radar_signal_analysis

MODULE_PATH = Path(__file__).resolve().parents[1] / "infra" / "scripts" / "seed_demo_data.py"
SPEC = importlib.util.spec_from_file_location("seed_demo_data", MODULE_PATH)
assert SPEC is not None
assert SPEC.loader is not None
seed_demo_data = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = seed_demo_data
SPEC.loader.exec_module(seed_demo_data)


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
async def test_seed_demo_data_populates_empty_database(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    fixed_now = datetime(2026, 5, 5, 16, 30, tzinfo=UTC)

    async with session_factory() as session:
        summary = await seed_demo_data.seed_demo_data(session, now=fixed_now)

        assert summary["status"] == "ok"
        assert summary["seed_key"] == seed_demo_data.DEMO_SEED_KEY
        assert summary["created"] == {
            "users": 1,
            "portfolio_holdings": 1,
            "watchlist_items": 1,
            "radar_scan_batches": 1,
            "radar_signals": 2,
            "signal_evidences": 3,
            "radar_signal_reviews": 2,
            "reports": 1,
        }
        assert summary["reused"] == {}

        assert await _count(session, UserProfile) == 1
        assert await _count(session, PortfolioHolding) == 1
        assert await _count(session, WatchlistItem) == 1
        assert await _count(session, RadarScanBatch) == 1
        assert await _count(session, RadarSignal) == 2
        assert await _count(session, SignalEvidence) == 3
        assert await _count(session, RadarSignalReview) == 2
        assert await _count(session, Report) == 1

        mainline_signal = await session.scalar(
            select(RadarSignal).where(
                RadarSignal.signal_key == seed_demo_data.MAINLINE_SIGNAL_KEY
            )
        )
        assert mainline_signal is not None
        assert mainline_signal.priority == "P1"
        assert mainline_signal.lifecycle_stage == "developing"
        assert mainline_signal.metrics["seed_key"] == seed_demo_data.DEMO_SEED_KEY

        analysis = await get_radar_signal_analysis(session, mainline_signal.id)
        assert analysis is not None
        assert analysis.signal_id == mainline_signal.id
        assert len(analysis.agent_assessments) == 5
        assert [agent.agent_id for agent in analysis.agent_assessments] == [
            "data_quality_agent",
            "risk_agent",
            "momentum_agent",
            "evidence_agent",
            "report_agent",
        ]


@pytest.mark.asyncio
async def test_seed_demo_data_is_idempotent(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    fixed_now = datetime(2026, 5, 5, 16, 30, tzinfo=UTC)

    async with session_factory() as session:
        first_summary = await seed_demo_data.seed_demo_data(session, now=fixed_now)
        second_summary = await seed_demo_data.seed_demo_data(session, now=fixed_now)

        assert first_summary["total_created"] == 12
        assert second_summary["created"] == {}
        assert second_summary["reused"] == {
            "users": 1,
            "portfolio_holdings": 1,
            "watchlist_items": 1,
            "radar_scan_batches": 1,
            "radar_signals": 2,
            "signal_evidences": 3,
            "radar_signal_reviews": 2,
            "reports": 1,
        }
        assert second_summary["total_reused"] == 12

        assert await _count(session, UserProfile) == 1
        assert await _count(session, PortfolioHolding) == 1
        assert await _count(session, WatchlistItem) == 1
        assert await _count(session, RadarScanBatch) == 1
        assert await _count(session, RadarSignal) == 2
        assert await _count(session, SignalEvidence) == 3
        assert await _count(session, RadarSignalReview) == 2
        assert await _count(session, Report) == 1


async def _count(session: AsyncSession, model: type[object]) -> int:
    count = await session.scalar(select(func.count()).select_from(model))
    assert count is not None
    return count
