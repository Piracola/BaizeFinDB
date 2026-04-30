from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta

import pytest
import pytest_asyncio
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.db.base import Base
from app.db.provider_models import DataQualityCheck, MarketSnapshot
from app.radar import service as radar_service
from app.radar.schemas import RadarPriority, RadarScanStatus
from app.radar.service import (
    get_latest_radar_scan,
    get_radar_overview,
    get_radar_scan,
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
async def test_radar_scan_carries_provider_quality_into_signal_and_evidence(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    async with session_factory() as session:
        snapshot = MarketSnapshot(
            provider_name="akshare",
            endpoint="stock_board_industry_name_em",
            market="A_SHARE",
            snapshot_type="sector_industry",
            source_time=None,
            collected_at=datetime.now(UTC),
            row_count=1,
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
                }
            ],
            normalization_version="test",
        )
        session.add(snapshot)
        await session.flush()
        session.add(
            DataQualityCheck(
                provider_name="akshare",
                endpoint="stock_board_industry_name_em",
                check_name="required_fields_and_row_count",
                status="degraded",
                confidence=0.45,
                missing_fields=["上涨家数"],
                details={
                    "row_count": 1,
                    "snapshot_type": "sector_industry",
                    "freshness": "unknown_source_time",
                },
                snapshot_id=snapshot.id,
            )
        )
        await session.commit()

        scan = await run_radar_scan(session)
        detail = await get_radar_signal_detail(session, scan.signals[0].id)

    assert scan.summary["data_quality"]["status_counts"] == {"degraded": 1}
    assert scan.summary["data_quality"]["degraded_snapshot_ids"] == [snapshot.id]

    signal_quality = scan.signals[0].metrics["provider_quality"]
    assert signal_quality["status"] == "degraded"
    assert signal_quality["confidence"] == 0.45
    assert signal_quality["missing_fields"] == ["上涨家数"]

    assert detail is not None
    evidence_quality = detail.evidences[0].details["provider_quality"]
    assert evidence_quality["status"] == "degraded"
    assert evidence_quality["snapshot_id"] == snapshot.id


@pytest.mark.asyncio
async def test_radar_scan_uses_latest_endpoint_failure_quality(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    async with session_factory() as session:
        snapshot = MarketSnapshot(
            provider_name="akshare",
            endpoint="stock_board_industry_name_em",
            market="A_SHARE",
            snapshot_type="sector_industry",
            source_time=None,
            collected_at=datetime.now(UTC),
            row_count=1,
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
                }
            ],
            normalization_version="test",
        )
        session.add(snapshot)
        await session.flush()
        session.add(
            DataQualityCheck(
                provider_name="akshare",
                endpoint="stock_board_industry_name_em",
                check_name="required_fields_and_row_count",
                status="ok",
                confidence=0.95,
                missing_fields=[],
                details={
                    "row_count": 1,
                    "snapshot_type": "sector_industry",
                    "freshness": "unknown_source_time",
                },
                snapshot_id=snapshot.id,
            )
        )
        await session.flush()
        session.add(
            DataQualityCheck(
                provider_name="akshare",
                endpoint="stock_board_industry_name_em",
                check_name="provider_fetch",
                status="failed",
                confidence=0.0,
                missing_fields=[],
                details={"error_message": "RuntimeError: upstream unavailable"},
                snapshot_id=None,
            )
        )
        await session.commit()

        scan = await run_radar_scan(session)

    signal_quality = scan.signals[0].metrics["provider_quality"]
    assert signal_quality["status"] == "failed"
    assert signal_quality["quality_scope"] == "latest_endpoint"
    assert signal_quality["snapshot_quality_status"] == "ok"
    assert signal_quality["latest_endpoint_quality_status"] == "failed"
    assert scan.summary["data_quality"]["status_counts"] == {"failed": 1}


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
async def test_radar_scan_records_failure_when_candidate_build_raises(
    session_factory: async_sessionmaker[AsyncSession],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def raise_candidate_build(
        snapshots: list[MarketSnapshot],
        snapshot_quality_summaries: dict[int, dict[str, object]] | None = None,
    ) -> list[object]:
        assert len(snapshots) == 1
        assert snapshot_quality_summaries is not None
        raise ValueError("bad normalized row")

    monkeypatch.setattr(radar_service, "_build_signal_candidates", raise_candidate_build)

    async with session_factory() as session:
        session.add(
            MarketSnapshot(
                provider_name="akshare",
                endpoint="stock_board_industry_name_em",
                market="A_SHARE",
                snapshot_type="sector_industry",
                source_time=None,
                collected_at=datetime.now(UTC),
                row_count=1,
                raw_summary={"columns": []},
                normalized_rows=[
                    {
                        "sector_code": "BK001",
                        "sector_name": "Broken Row",
                        "pct_change": 6.2,
                        "rising_count": 24,
                        "falling_count": 4,
                    }
                ],
                normalization_version="test",
            )
        )
        await session.commit()

        scan = await run_radar_scan(session)
        loaded_scan = await get_radar_scan(session, scan.id)
        latest_scan = await get_latest_radar_scan(session)

    assert scan.status == RadarScanStatus.FAILURE
    assert scan.finished_at is not None
    assert scan.error_message == "ValueError: bad normalized row"
    assert scan.summary["error_type"] == "ValueError"
    assert scan.summary["source_snapshot_count"] == 1
    assert scan.signals == []

    assert loaded_scan is not None
    assert loaded_scan.status == RadarScanStatus.FAILURE
    assert latest_scan is not None
    assert latest_scan.id == scan.id
    assert latest_scan.status != RadarScanStatus.RUNNING


@pytest.mark.asyncio
async def test_radar_scan_reraises_database_errors(
    session_factory: async_sessionmaker[AsyncSession],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def raise_database_error(session: AsyncSession) -> list[MarketSnapshot]:
        raise SQLAlchemyError("database is unavailable")

    monkeypatch.setattr(radar_service, "_load_latest_source_snapshots", raise_database_error)

    async with session_factory() as session:
        with pytest.raises(SQLAlchemyError):
            await run_radar_scan(session)

        latest_scan = await get_latest_radar_scan(session)

    assert latest_scan is not None
    assert latest_scan.status == RadarScanStatus.FAILURE
    assert latest_scan.summary["error_type"] == "SQLAlchemyError"


@pytest.mark.asyncio
async def test_radar_overview_dedupes_subjects_and_counts_priorities(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    first_collected_at = datetime.now(UTC)

    async with session_factory() as session:
        session.add(
            MarketSnapshot(
                provider_name="akshare",
                endpoint="stock_board_concept_name_em",
                market="A_SHARE",
                snapshot_type="sector_concept",
                source_time=None,
                collected_at=first_collected_at,
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
        first_scan = await run_radar_scan(session)

        session.add(
            MarketSnapshot(
                provider_name="akshare",
                endpoint="stock_board_concept_name_em",
                market="A_SHARE",
                snapshot_type="sector_concept",
                source_time=None,
                collected_at=first_collected_at + timedelta(minutes=5),
                row_count=2,
                raw_summary={"columns": []},
                normalized_rows=[
                    {
                        "sector_code": "GN001",
                        "sector_name": "AI Applications",
                        "pct_change": 6.1,
                        "turnover_rate": 4.1,
                        "rising_count": 24,
                        "falling_count": 4,
                        "leading_stock": "Example AI",
                        "leading_stock_pct_change": 9.2,
                    },
                    {
                        "sector_code": "GN002",
                        "sector_name": "Cloud Tools",
                        "pct_change": 1.8,
                        "turnover_rate": 2.0,
                        "rising_count": 10,
                        "falling_count": 9,
                        "leading_stock": "Example Cloud",
                        "leading_stock_pct_change": 4.0,
                    },
                ],
                normalization_version="test",
            )
        )
        await session.commit()
        second_scan = await run_radar_scan(session)

        loaded_scan = await get_radar_scan(session, second_scan.id)
        overview = await get_radar_overview(session, limit=10)
        limited_overview = await get_radar_overview(session, limit=1)

    assert loaded_scan is not None
    assert loaded_scan.id == second_scan.id
    assert overview.latest_scan is not None
    assert overview.latest_scan.id == second_scan.id
    assert overview.subject_count == 2
    assert overview.priority_counts == {"P0": 1, "P1": 0, "P2": 1}

    ai_subjects = [
        subject for subject in overview.current_subjects if subject.subject_code == "GN001"
    ]
    assert len(ai_subjects) == 1
    assert ai_subjects[0].latest_signal.id != first_scan.signals[0].id
    assert ai_subjects[0].latest_signal.priority == RadarPriority.P0
    assert {signal.subject_code for signal in overview.active_signals} == {"GN001", "GN002"}
    assert len(limited_overview.active_signals) == 1
    assert limited_overview.subject_count == 2
    assert limited_overview.priority_counts == {"P0": 1, "P1": 0, "P2": 1}


@pytest.mark.asyncio
async def test_radar_overview_uses_latest_scan_only(
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
                        "sector_code": "BK001",
                        "sector_name": "Semiconductors",
                        "pct_change": 6.2,
                        "turnover_rate": 4.8,
                        "rising_count": 24,
                        "falling_count": 4,
                        "leading_stock": "Example Tech",
                        "leading_stock_pct_change": 10.0,
                    }
                ],
                normalization_version="test",
            )
        )
        await session.commit()
        await run_radar_scan(session)

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
                        "sector_code": "BK001",
                        "sector_name": "Semiconductors",
                        "pct_change": 0.2,
                        "turnover_rate": 1.2,
                        "rising_count": 3,
                        "falling_count": 20,
                        "leading_stock": "Example Tech",
                        "leading_stock_pct_change": 1.0,
                    }
                ],
                normalization_version="test",
            )
        )
        await session.commit()
        quiet_scan = await run_radar_scan(session)
        overview = await get_radar_overview(session)

    assert quiet_scan.status == RadarScanStatus.NO_DATA
    assert overview.latest_scan is not None
    assert overview.latest_scan.id == quiet_scan.id
    assert overview.active_signals == []
    assert overview.current_subjects == []
    assert overview.subject_count == 0
    assert overview.priority_counts == {"P0": 0, "P1": 0, "P2": 0}


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
