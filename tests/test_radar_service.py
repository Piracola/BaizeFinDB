from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta

import pytest
import pytest_asyncio
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.core.config import get_settings
from app.db.base import Base
from app.db.provider_models import DataQualityCheck, MarketSnapshot
from app.db.radar_models import RadarScanBatch, RadarSignal
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
async def test_radar_scan_does_not_create_mainline_p0_from_news_only_snapshot(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    async with session_factory() as session:
        session.add(
            MarketSnapshot(
                provider_name="manual",
                endpoint="news_flash",
                market="A_SHARE",
                snapshot_type="news_event",
                source_time=None,
                collected_at=datetime.now(UTC),
                row_count=1,
                raw_summary={"columns": []},
                normalized_rows=[
                    {
                        "title": "Rumor headline without market confirmation",
                        "event_type": "market_news",
                        "severity": "major",
                        "severity_score": 0.95,
                    }
                ],
                normalization_version="test",
            )
        )
        await session.commit()

        scan = await run_radar_scan(session)
        p0_signals = await list_radar_signals(session, priority=RadarPriority.P0)

    assert scan.status == RadarScanStatus.NO_DATA
    assert scan.summary["candidate_count"] == 0
    assert scan.summary["source_snapshot_count"] == 0
    assert scan.signals == []
    assert p0_signals == []


@pytest.mark.asyncio
async def test_radar_scan_generates_risk_p0_from_major_event_snapshot(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    async with session_factory() as session:
        session.add(
            MarketSnapshot(
                provider_name="manual",
                endpoint="risk_events",
                market="A_SHARE",
                snapshot_type="risk_event",
                source_time=None,
                collected_at=datetime.now(UTC),
                row_count=1,
                raw_summary={"columns": []},
                normalized_rows=[
                    {
                        "event_id": "risk-001",
                        "event_name": "重大监管风险事件",
                        "event_type": "regulatory",
                        "severity": "major",
                        "severity_score": 0.9,
                        "source_label": "manual-fixture",
                    }
                ],
                normalization_version="test",
            )
        )
        await session.commit()

        scan = await run_radar_scan(session)
        detail = await get_radar_signal_detail(session, scan.signals[0].id)

    assert scan.status == RadarScanStatus.SUCCESS
    assert scan.summary["candidate_count"] == 1
    assert scan.summary["priority_counts"]["P0"] == 1
    assert scan.signals[0].priority == RadarPriority.P0
    assert scan.signals[0].subject_type == "risk_event"
    assert scan.signals[0].subject_name == "重大监管风险事件"
    assert scan.signals[0].metrics["risk_event_type"] == "regulatory"
    assert "risk_event_type_regulatory" in scan.signals[0].metrics["rule_reasons"]
    assert "risk_severity_major" in scan.signals[0].metrics["rule_reasons"]

    assert detail is not None
    assert detail.evidences[0].evidence_type == "risk_event"
    assert detail.evidences[0].source_name == "manual"
    assert detail.evidences[0].details["metrics"]["severity_score"] == 0.9


@pytest.mark.asyncio
async def test_radar_scan_maps_major_tushare_announcement_to_risk_p0(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    async with session_factory() as session:
        session.add(
            MarketSnapshot(
                provider_name="tushare",
                endpoint="anns_d",
                market="A_SHARE",
                snapshot_type="announcements",
                source_time=None,
                collected_at=datetime.now(UTC),
                row_count=2,
                raw_summary={"columns": []},
                normalized_rows=[
                    {
                        "ann_date": "20260503",
                        "ts_code": "000001.SZ",
                        "name": "风险样例",
                        "title": "关于收到中国证监会立案调查通知书的公告",
                        "url": "https://example.invalid/internal-only",
                    },
                    {
                        "ann_date": "20260503",
                        "ts_code": "000002.SZ",
                        "name": "普通样例",
                        "title": "董事会决议公告",
                    },
                ],
                normalization_version="test",
            )
        )
        await session.commit()

        scan = await run_radar_scan(session)
        detail = await get_radar_signal_detail(session, scan.signals[0].id)

    assert scan.status == RadarScanStatus.SUCCESS
    assert scan.summary["candidate_count"] == 1
    assert scan.summary["priority_counts"]["P0"] == 1
    assert scan.summary["source_endpoints"] == ["anns_d"]
    assert scan.signals[0].priority == RadarPriority.P0
    assert scan.signals[0].subject_type == "announcements"
    assert scan.signals[0].subject_code == "000001.SZ"
    assert scan.signals[0].subject_name == "关于收到中国证监会立案调查通知书的公告"
    assert scan.signals[0].metrics["risk_event_type"] == "major_announcement"
    assert scan.signals[0].metrics["source_label"] == "tushare:anns_d"
    assert "立案调查" in scan.signals[0].metrics["announcement_keywords"]
    assert "risk_event_type_major_announcement" in scan.signals[0].metrics["rule_reasons"]

    assert detail is not None
    assert detail.evidences[0].evidence_type == "risk_event"
    assert detail.evidences[0].source_name == "tushare"
    assert detail.evidences[0].public_share_policy == "internal_summary_only"


@pytest.mark.asyncio
async def test_radar_scan_carries_limit_pool_sentiment_into_mainline_signal(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    now = datetime.now(UTC)
    async with session_factory() as session:
        session.add_all(
            [
                MarketSnapshot(
                    provider_name="akshare",
                    endpoint="stock_board_concept_name_em",
                    market="A_SHARE",
                    snapshot_type="sector_concept",
                    source_time=None,
                    collected_at=now,
                    row_count=1,
                    raw_summary={"columns": []},
                    normalized_rows=[
                        {
                            "sector_code": "GN001",
                            "sector_name": "AI Applications",
                            "pct_change": 3.8,
                            "rising_count": 18,
                            "falling_count": 6,
                            "leading_stock": "Example AI",
                            "leading_stock_pct_change": 8.5,
                        }
                    ],
                    normalization_version="test",
                ),
                _sentiment_snapshot("stock_zt_pool_em", "limit_up_pool", 12, now),
                _sentiment_snapshot("stock_zt_pool_dtgc_em", "limit_down_pool", 2, now),
                _sentiment_snapshot("stock_zt_pool_zbgc_em", "broken_limit_up_pool", 3, now),
            ]
        )
        await session.commit()

        scan = await run_radar_scan(session)
        detail = await get_radar_signal_detail(session, scan.signals[0].id)

    sentiment = scan.summary["market_sentiment"]
    assert sentiment == {
        "limit_up_count": 12,
        "limit_down_count": 2,
        "broken_limit_up_count": 3,
        "net_limit_pressure": 7,
        "sentiment_bias": "positive",
    }

    signal_sentiment = scan.signals[0].metrics["market_sentiment"]
    assert signal_sentiment["limit_up_count"] == 12
    assert scan.signals[0].metrics["sentiment_confirmation"] == "positive_limit_up_pressure"

    assert detail is not None
    evidence_metrics = detail.evidences[0].details["metrics"]
    assert evidence_metrics["market_sentiment"]["sentiment_bias"] == "positive"


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
        market_sentiment: dict[str, object] | None = None,
    ) -> list[object]:
        assert len(snapshots) == 1
        assert snapshot_quality_summaries is not None
        assert market_sentiment is not None
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
    assert overview.lifecycle_counts["developing"] == 1
    assert overview.lifecycle_counts["ignition"] == 1
    stock_backtrace_names = [
        evidence.stock_name for evidence in overview.stock_backtrace_evidences
    ]
    assert stock_backtrace_names == ["Example AI", "Example Cloud"]
    assert overview.stock_backtrace_evidences[0].stock_pct_change == 9.2
    assert overview.stock_backtrace_evidences[0].subject_name == "AI Applications"

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
    assert limited_overview.lifecycle_counts["developing"] == 1
    assert limited_overview.lifecycle_counts["ignition"] == 1
    limited_backtrace_subjects = [
        evidence.subject_name for evidence in limited_overview.stock_backtrace_evidences
    ]
    assert limited_backtrace_subjects == ["AI Applications"]


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
    assert all(count == 0 for count in overview.lifecycle_counts.values())
    assert overview.stock_backtrace_evidences == []


@pytest.mark.asyncio
async def test_radar_signal_list_hides_expired_p2_by_default(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    now = datetime(2026, 1, 10, tzinfo=UTC)

    async with session_factory() as session:
        scan = RadarScanBatch(
            status="success",
            started_at=now,
            finished_at=now,
            source_snapshot_ids=[],
            summary={"priority_counts": {"P0": 0, "P1": 1, "P2": 2}},
        )
        session.add(scan)
        await session.flush()
        session.add_all(
            [
                _manual_signal(
                    batch_id=scan.id,
                    signal_key="test:p2:expired",
                    subject_name="Expired P2 Theme",
                    priority="P2",
                    created_at=now - timedelta(days=8),
                ),
                _manual_signal(
                    batch_id=scan.id,
                    signal_key="test:p2:recent",
                    subject_name="Recent P2 Theme",
                    priority="P2",
                    created_at=now - timedelta(days=6, hours=23),
                ),
                _manual_signal(
                    batch_id=scan.id,
                    signal_key="test:p1:old",
                    subject_name="Old P1 Theme",
                    priority="P1",
                    created_at=now - timedelta(days=30),
                ),
            ]
        )
        await session.commit()

        default_signals = await list_radar_signals(session, as_of=now)
        p2_signals = await list_radar_signals(
            session,
            priority=RadarPriority.P2,
            as_of=now,
        )
        historical_signals = await list_radar_signals(
            session,
            priority=RadarPriority.P2,
            include_expired_p2=True,
            as_of=now,
        )

    assert {signal.subject_name for signal in default_signals} == {
        "Recent P2 Theme",
        "Old P1 Theme",
    }
    assert [signal.subject_name for signal in p2_signals] == ["Recent P2 Theme"]
    assert {signal.subject_name for signal in historical_signals} == {
        "Expired P2 Theme",
        "Recent P2 Theme",
    }


@pytest.mark.asyncio
async def test_radar_overview_hides_expired_p2_from_current_view(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    now = datetime(2026, 1, 10, tzinfo=UTC)

    async with session_factory() as session:
        scan = RadarScanBatch(
            status="success",
            started_at=now - timedelta(days=8),
            finished_at=now - timedelta(days=8),
            source_snapshot_ids=[],
            summary={"priority_counts": {"P0": 0, "P1": 1, "P2": 1}},
        )
        session.add(scan)
        await session.flush()
        session.add_all(
            [
                _manual_signal(
                    batch_id=scan.id,
                    signal_key="test:p2:expired-overview",
                    subject_name="Expired P2 Theme",
                    priority="P2",
                    created_at=now - timedelta(days=8),
                ),
                _manual_signal(
                    batch_id=scan.id,
                    signal_key="test:p1:old-overview",
                    subject_name="Old P1 Theme",
                    priority="P1",
                    created_at=now - timedelta(days=8),
                ),
            ]
        )
        await session.commit()

        overview = await get_radar_overview(session, as_of=now)

    assert overview.latest_scan is not None
    assert [signal.subject_name for signal in overview.latest_scan.signals] == [
        "Old P1 Theme"
    ]
    assert overview.subject_count == 1
    assert overview.priority_counts == {"P0": 0, "P1": 1, "P2": 0}
    assert overview.lifecycle_counts["developing"] == 1
    assert [subject.subject_name for subject in overview.current_subjects] == [
        "Old P1 Theme"
    ]


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
async def test_radar_scan_uses_configured_p1_trigger_count(
    session_factory: async_sessionmaker[AsyncSession],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("RADAR_CONTINUOUS_P1_TRIGGER_COUNT", "2")
    get_settings.cache_clear()

    try:
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
            scan = await run_radar_scan(session)
    finally:
        get_settings.cache_clear()

    assert scan.summary["continuous_p1_trigger_count"] == 2
    assert scan.summary["quick_report_candidate_count"] == 1
    assert scan.signals[0].priority == RadarPriority.P1
    continuity = scan.signals[0].metrics["continuity"]
    assert continuity["consecutive_p1_count"] == 2
    assert continuity["quick_report_candidate"] is True


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


def _manual_signal(
    *,
    batch_id: int,
    signal_key: str,
    subject_name: str,
    priority: str,
    created_at: datetime,
) -> RadarSignal:
    return RadarSignal(
        batch_id=batch_id,
        signal_key=signal_key,
        subject_type="sector_concept",
        subject_code=None,
        subject_name=subject_name,
        priority=priority,
        lifecycle_stage="developing",
        review_status="candidate",
        title=f"{priority} radar candidate: {subject_name}",
        summary="Manual signal for retention tests.",
        metrics={"pct_change": 1.2},
        evidence_count=0,
        created_at=created_at,
    )


def _sentiment_snapshot(
    endpoint: str,
    snapshot_type: str,
    row_count: int,
    collected_at: datetime,
) -> MarketSnapshot:
    return MarketSnapshot(
        provider_name="akshare",
        endpoint=endpoint,
        market="A_SHARE",
        snapshot_type=snapshot_type,
        source_time=None,
        collected_at=collected_at,
        row_count=row_count,
        raw_summary={"columns": []},
        normalized_rows=[{"name": f"{snapshot_type} fixture"} for _ in range(row_count)],
        normalization_version="test",
    )
