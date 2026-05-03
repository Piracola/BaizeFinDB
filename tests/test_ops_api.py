from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.db.audit_models import ModelCallLog
from app.db.base import Base
from app.db.portfolio_models import UserProfile
from app.db.provider_models import DataQualityCheck, ProviderFetchLog
from app.db.push_models import PushLog
from app.db.radar_models import RadarScanBatch
from app.db.session import get_db_session
from app.main import create_app


@pytest.fixture(autouse=True)
def stable_disk_usage(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "app.ops.service.shutil.disk_usage",
        lambda path: SimpleNamespace(total=1_000_000, used=400_000, free=600_000),
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
async def test_ops_overview_summarizes_recent_runtime_signals(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    now = datetime.now(UTC)
    async with session_factory() as session:
        user = UserProfile(user_key="ops-user", display_name="Ops User")
        session.add(user)
        await session.flush()

        latest_scan = RadarScanBatch(
            status="success",
            started_at=now - timedelta(minutes=5),
            finished_at=now - timedelta(minutes=4),
            source_snapshot_ids=[1],
            summary={"signal_count": 2},
        )
        session.add_all(
            [
                latest_scan,
                RadarScanBatch(
                    status="failure",
                    started_at=now - timedelta(hours=1),
                    finished_at=now - timedelta(minutes=59),
                    source_snapshot_ids=[],
                    summary={"error_type": "ProviderError"},
                    error_message="provider down",
                ),
                RadarScanBatch(
                    status="failure",
                    started_at=now - timedelta(days=3),
                    finished_at=now - timedelta(days=3) + timedelta(minutes=1),
                    source_snapshot_ids=[],
                    summary={},
                ),
            ],
        )
        session.add_all(
            [
                ProviderFetchLog(
                    provider_name="akshare",
                    endpoint="stock_zh_a_spot_em",
                    status="success",
                    fetch_started_at=now - timedelta(minutes=10),
                    fetch_finished_at=now - timedelta(minutes=9),
                    source_time=None,
                    row_count=100,
                    error_message=None,
                    freshness="unknown_source_time",
                    confidence=0.95,
                    missing_fields=[],
                    raw_snapshot_id=None,
                    normalization_version="test",
                ),
                ProviderFetchLog(
                    provider_name="akshare",
                    endpoint="stock_board_concept_name_em",
                    status="failure",
                    fetch_started_at=now - timedelta(minutes=8),
                    fetch_finished_at=now - timedelta(minutes=7),
                    source_time=None,
                    row_count=0,
                    error_message="network",
                    freshness="unavailable",
                    confidence=0.0,
                    missing_fields=[],
                    raw_snapshot_id=None,
                    normalization_version="test",
                ),
            ],
        )
        session.add_all(
            [
                DataQualityCheck(
                    provider_name="akshare",
                    endpoint="stock_zh_a_spot_em",
                    check_name="normalization",
                    status="ok",
                    confidence=0.95,
                    missing_fields=[],
                    details={},
                    created_at=now - timedelta(minutes=9),
                ),
                DataQualityCheck(
                    provider_name="akshare",
                    endpoint="stock_board_concept_name_em",
                    check_name="normalization",
                    status="degraded",
                    confidence=0.45,
                    missing_fields=["rising_count"],
                    details={},
                    created_at=now - timedelta(minutes=7),
                ),
            ],
        )
        session.add_all(
            [
                PushLog(
                    user_id=user.id,
                    channel="telegram",
                    target_ref="1001",
                    source_kind="radar_scan",
                    source_id=1,
                    status="sent",
                    title="push sent",
                    message_text="sent",
                    included_signal_ids=[],
                    blocked_signal_ids=[],
                    needs_human_review_signal_ids=[],
                    delivery_details={},
                    created_at=now - timedelta(minutes=6),
                ),
                PushLog(
                    user_id=user.id,
                    channel="telegram",
                    target_ref="1001",
                    source_kind="radar_scan",
                    source_id=2,
                    status="failure",
                    title="push failed",
                    message_text="failed",
                    included_signal_ids=[],
                    blocked_signal_ids=[],
                    needs_human_review_signal_ids=[],
                    delivery_details={},
                    created_at=now - timedelta(minutes=5),
                ),
            ],
        )
        session.add_all(
            [
                ModelCallLog(
                    call_site="review",
                    primary_model="primary",
                    fallback_model=None,
                    status="degraded",
                    error_type="TimeoutError",
                    error_message="timeout",
                    prompt_hash="a" * 64,
                    prompt_length=200,
                    raw_prompt=None,
                    response_excerpt=None,
                    details={},
                    created_at=now - timedelta(minutes=4),
                ),
                ModelCallLog(
                    call_site="report",
                    primary_model="primary",
                    fallback_model="fallback",
                    status="fallback",
                    error_type="RateLimitError",
                    error_message="rate limit",
                    prompt_hash="b" * 64,
                    prompt_length=300,
                    raw_prompt=None,
                    response_excerpt=None,
                    details={},
                    created_at=now - timedelta(minutes=3),
                ),
            ],
        )
        await session.commit()
        latest_scan_id = latest_scan.id

    response = await _get_ops_overview(session_factory, lookback_hours=24)

    assert response.status_code == 200
    payload = response.json()
    assert payload["lookback_hours"] == 24
    assert payload["server"]["process_id"] >= 0
    assert payload["server"]["disk_free_percent"] == 60.0
    assert payload["server"]["is_disk_space_low"] is False
    assert payload["radar"]["latest_scan_id"] == latest_scan_id
    assert payload["radar"]["latest_scan_status"] == "success"
    assert payload["radar"]["latest_scan_duration_seconds"] == 60.0
    assert payload["radar"]["recent_scan_count"] == 2
    assert payload["radar"]["recent_scan_failure_count"] == 1
    assert payload["radar"]["recent_scan_failure_rate"] == 0.5
    assert payload["radar"]["is_latest_scan_stale"] is False
    assert payload["provider_fetch"]["status_counts"] == {"failure": 1, "success": 1}
    assert payload["provider_fetch"]["unhealthy_count"] == 1
    assert payload["data_quality"]["status_counts"] == {"degraded": 1, "ok": 1}
    assert payload["data_quality"]["unhealthy_count"] == 1
    assert payload["telegram_push"]["status_counts"] == {"failure": 1, "sent": 1}
    assert payload["telegram_push"]["unhealthy_count"] == 1
    assert payload["model_calls"]["status_counts"] == {"degraded": 1, "fallback": 1}
    assert payload["model_calls"]["unhealthy_count"] == 2
    assert [alert["code"] for alert in payload["alerts"]] == [
        "radar_failure_rate_high",
        "provider_fetch_unhealthy",
        "data_quality_unhealthy",
        "telegram_push_unhealthy",
        "model_calls_unhealthy",
    ]


@pytest.mark.asyncio
async def test_ops_overview_handles_empty_database(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    response = await _get_ops_overview(session_factory, lookback_hours=1)

    assert response.status_code == 200
    payload = response.json()
    assert payload["server"]["disk_free_percent"] == 60.0
    assert payload["radar"]["latest_scan_id"] is None
    assert payload["radar"]["recent_scan_count"] == 0
    assert payload["radar"]["is_latest_scan_stale"] is True
    assert payload["provider_fetch"]["total_count"] == 0
    assert payload["data_quality"]["total_count"] == 0
    assert payload["telegram_push"]["total_count"] == 0
    assert payload["model_calls"]["total_count"] == 0
    assert payload["alerts"] == [
        {
            "severity": "warning",
            "code": "radar_no_scan",
            "message": "尚未找到雷达扫描记录。",
        }
    ]


@pytest.mark.asyncio
async def test_ops_history_lists_recent_runtime_failures(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    now = datetime.now(UTC)
    async with session_factory() as session:
        user = UserProfile(user_key="ops-history-user", display_name="Ops History User")
        session.add(user)
        await session.flush()
        session.add_all(
            [
                RadarScanBatch(
                    status="success",
                    started_at=now - timedelta(minutes=5),
                    finished_at=now - timedelta(minutes=4),
                    source_snapshot_ids=[1, 2],
                    summary={"signal_count": 3},
                ),
                RadarScanBatch(
                    status="failure",
                    started_at=now - timedelta(minutes=15),
                    finished_at=now - timedelta(minutes=14),
                    source_snapshot_ids=[],
                    summary={"error_type": "ProviderError"},
                    error_message="provider unavailable",
                ),
                ProviderFetchLog(
                    provider_name="akshare",
                    endpoint="stock_board_concept_name_em",
                    status="failure",
                    fetch_started_at=now - timedelta(minutes=12),
                    fetch_finished_at=now - timedelta(minutes=11),
                    source_time=None,
                    row_count=0,
                    error_message="network",
                    freshness="unavailable",
                    confidence=0.0,
                    missing_fields=[],
                    raw_snapshot_id=None,
                    normalization_version="test",
                ),
                DataQualityCheck(
                    provider_name="akshare",
                    endpoint="stock_zh_a_spot_em",
                    check_name="normalization",
                    status="degraded",
                    confidence=0.4,
                    missing_fields=["amount"],
                    details={},
                    created_at=now - timedelta(minutes=10),
                ),
                PushLog(
                    user_id=user.id,
                    channel="telegram",
                    target_ref="1001",
                    source_kind="radar_scan",
                    source_id=1,
                    status="failure",
                    title="push failed",
                    message_text="failed",
                    included_signal_ids=[],
                    blocked_signal_ids=[],
                    needs_human_review_signal_ids=[],
                    delivery_details={},
                    created_at=now - timedelta(minutes=9),
                ),
                ModelCallLog(
                    call_site="review",
                    primary_model="primary",
                    fallback_model="fallback",
                    status="fallback",
                    error_type="RateLimitError",
                    error_message="rate limit",
                    prompt_hash="c" * 64,
                    prompt_length=100,
                    raw_prompt=None,
                    response_excerpt=None,
                    details={},
                    created_at=now - timedelta(minutes=8),
                ),
            ],
        )
        await session.commit()

    response = await _get_ops_history(session_factory, lookback_hours=24, limit=10)

    assert response.status_code == 200
    payload = response.json()
    assert payload["lookback_hours"] == 24
    assert payload["limit"] == 10
    kinds = [event["kind"] for event in payload["recent_events"]]
    assert "radar_scan" in kinds
    assert "provider_fetch" in kinds
    assert "data_quality" in kinds
    assert "telegram_push" in kinds
    assert "model_call" in kinds
    assert payload["recent_events"][0]["kind"] == "radar_scan"
    model_event = next(event for event in payload["recent_events"] if event["kind"] == "model_call")
    assert model_event["metadata"]["error_type"] == "RateLimitError"
    failure_keys = {
        (item["kind"], item["key"]): item["count"]
        for item in payload["failure_summary"]
    }
    assert failure_keys[("radar_scan", "failure")] == 1
    assert failure_keys[("provider_fetch", "akshare/stock_board_concept_name_em/failure")] == 1
    assert failure_keys[("data_quality", "akshare/stock_zh_a_spot_em/degraded")] == 1
    assert failure_keys[("telegram_push", "telegram/failure")] == 1
    assert failure_keys[("model_call", "review/fallback/RateLimitError")] == 1


@pytest.mark.asyncio
async def test_ops_overview_alerts_when_server_disk_space_is_low(
    monkeypatch: pytest.MonkeyPatch,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    monkeypatch.setattr(
        "app.ops.service.shutil.disk_usage",
        lambda path: SimpleNamespace(total=1_000_000, used=950_000, free=50_000),
    )

    response = await _get_ops_overview(session_factory, lookback_hours=1)

    assert response.status_code == 200
    payload = response.json()
    assert payload["server"]["disk_free_percent"] == 5.0
    assert payload["server"]["is_disk_space_low"] is True
    assert "server_disk_space_low" in [alert["code"] for alert in payload["alerts"]]


async def _get_ops_overview(
    session_factory: async_sessionmaker[AsyncSession],
    *,
    lookback_hours: int,
):
    app = create_app()

    async def override_db_session() -> AsyncIterator[AsyncSession]:
        async with session_factory() as session:
            yield session

    app.dependency_overrides[get_db_session] = override_db_session

    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            return await client.get(
                "/ops/overview",
                params={"lookback_hours": lookback_hours},
            )
    finally:
        app.dependency_overrides.clear()


async def _get_ops_history(
    session_factory: async_sessionmaker[AsyncSession],
    *,
    lookback_hours: int,
    limit: int,
):
    app = create_app()

    async def override_db_session() -> AsyncIterator[AsyncSession]:
        async with session_factory() as session:
            yield session

    app.dependency_overrides[get_db_session] = override_db_session

    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            return await client.get(
                "/ops/history",
                params={"lookback_hours": lookback_hours, "limit": limit},
            )
    finally:
        app.dependency_overrides.clear()
