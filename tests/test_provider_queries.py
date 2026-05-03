from collections.abc import AsyncIterator

import pandas as pd
import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.core.config import get_settings
from app.db.base import Base
from app.db.session import get_db_session
from app.main import create_app
from app.providers.akshare import AKSHARE_ENDPOINTS, normalize_dataframe
from app.providers.schemas import DataQualityStatus, ProviderStatus
from app.providers.service import (
    collect_akshare_endpoint,
    collect_tushare_endpoint,
    get_akshare_collection_status,
    get_tushare_readiness,
    list_latest_provider_snapshots,
    list_provider_fetch_logs,
)
from app.providers.tushare import (
    TUSHARE_ENDPOINTS,
)
from app.providers.tushare import (
    normalize_dataframe as normalize_tushare_dataframe,
)


class SuccessfulStockProvider:
    async def fetch(self, endpoint: str):
        dataframe = pd.DataFrame(
            [
                {
                    "代码": "600000",
                    "名称": "浦发银行",
                    "最新价": 8.12,
                    "涨跌幅": 1.25,
                    "成交额": 12345678.0,
                    "换手率": 0.8,
                }
            ]
        )
        return normalize_dataframe(dataframe, AKSHARE_ENDPOINTS[endpoint])


class SuccessfulTushareStockProvider:
    async def fetch(self, endpoint: str, **kwargs):
        dataframe = pd.DataFrame(
            [
                {
                    "ts_code": "600000.SH",
                    "symbol": "600000",
                    "name": "浦发银行",
                    "area": "上海",
                    "industry": "银行",
                    "market": "主板",
                    "exchange": "SSE",
                    "list_status": "L",
                    "list_date": "19991110",
                    "is_hs": "H",
                }
            ]
        )
        return normalize_tushare_dataframe(dataframe, TUSHARE_ENDPOINTS[endpoint])


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
async def test_provider_success_can_be_queried_from_database(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    async with session_factory() as session:
        result = await collect_akshare_endpoint(
            session,
            SuccessfulStockProvider(),
            "stock_zh_a_spot_em",
        )

        assert result.status == ProviderStatus.SUCCESS

        logs = await list_provider_fetch_logs(session)
        snapshots = await list_latest_provider_snapshots(
            session,
            endpoint="stock_zh_a_spot_em",
        )
        status = await get_akshare_collection_status(session)

    assert logs[0].status == ProviderStatus.SUCCESS
    assert logs[0].row_count == 1
    assert snapshots[0].preview_rows[0]["symbol"] == "600000"

    stock_status = next(
        item for item in status.endpoints if item.endpoint == "stock_zh_a_spot_em"
    )
    assert stock_status.latest_status == ProviderStatus.SUCCESS
    assert stock_status.latest_quality_status == DataQualityStatus.OK
    assert stock_status.latest_snapshot_id == result.snapshot_id


@pytest.mark.asyncio
async def test_provider_query_api_returns_database_state(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    async with session_factory() as session:
        await collect_akshare_endpoint(
            session,
            SuccessfulStockProvider(),
            "stock_zh_a_spot_em",
        )

    app = create_app()

    async def override_db_session() -> AsyncIterator[AsyncSession]:
        async with session_factory() as session:
            yield session

    app.dependency_overrides[get_db_session] = override_db_session

    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            status_response = await client.get("/providers/akshare/status")
            logs_response = await client.get("/providers/akshare/fetch-logs")
            snapshots_response = await client.get(
                "/providers/akshare/snapshots/latest",
                params={"endpoint": "stock_zh_a_spot_em"},
            )
            unknown_response = await client.get(
                "/providers/akshare/fetch-logs",
                params={"endpoint": "not_real"},
            )
    finally:
        app.dependency_overrides.clear()

    assert status_response.status_code == 200
    stock_status = next(
        item
        for item in status_response.json()["endpoints"]
        if item["endpoint"] == "stock_zh_a_spot_em"
    )
    assert stock_status["latest_status"] == "success"
    assert stock_status["latest_quality_status"] == "ok"

    assert logs_response.status_code == 200
    assert logs_response.json()[0]["endpoint"] == "stock_zh_a_spot_em"

    assert snapshots_response.status_code == 200
    assert snapshots_response.json()[0]["preview_rows"][0]["symbol"] == "600000"

    assert unknown_response.status_code == 404


@pytest.mark.asyncio
async def test_tushare_query_api_returns_database_state(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    async with session_factory() as session:
        await collect_tushare_endpoint(
            session,
            SuccessfulTushareStockProvider(),
            "stock_basic",
        )

    app = create_app()

    async def override_db_session() -> AsyncIterator[AsyncSession]:
        async with session_factory() as session:
            yield session

    app.dependency_overrides[get_db_session] = override_db_session

    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            logs_response = await client.get(
                "/providers/tushare/fetch-logs",
                params={"endpoint": "stock_basic"},
            )
            snapshots_response = await client.get(
                "/providers/tushare/snapshots/latest",
                params={"endpoint": "stock_basic"},
            )
            unknown_response = await client.get(
                "/providers/tushare/fetch-logs",
                params={"endpoint": "not_real"},
            )
    finally:
        app.dependency_overrides.clear()

    assert logs_response.status_code == 200
    assert logs_response.json()[0]["provider_name"] == "tushare"
    assert logs_response.json()[0]["endpoint"] == "stock_basic"

    assert snapshots_response.status_code == 200
    assert snapshots_response.json()[0]["provider_name"] == "tushare"
    assert snapshots_response.json()[0]["preview_rows"][0]["ts_code"] == "600000.SH"

    assert unknown_response.status_code == 404


@pytest.mark.asyncio
async def test_tushare_readiness_blocks_without_token(
    monkeypatch: pytest.MonkeyPatch,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    monkeypatch.delenv("TUSHARE_TOKEN", raising=False)
    get_settings.cache_clear()

    try:
        async with session_factory() as session:
            readiness = await get_tushare_readiness(session)
    finally:
        get_settings.cache_clear()

    assert readiness.status == "blocked"
    assert readiness.token_configured is False
    assert readiness.scheduler_ready_endpoint_count == 0
    assert readiness.endpoints[0].manual_fetch_eligible is False
    token_check = next(check for check in readiness.endpoints[0].checks if check.name == "token")
    assert token_check.status == "fail"


@pytest.mark.asyncio
async def test_tushare_readiness_api_returns_database_state(
    monkeypatch: pytest.MonkeyPatch,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    monkeypatch.setenv("TUSHARE_TOKEN", "secret-tushare-token")
    get_settings.cache_clear()

    async with session_factory() as session:
        await collect_tushare_endpoint(
            session,
            SuccessfulTushareStockProvider(),
            "stock_basic",
        )

    app = create_app()

    async def override_db_session() -> AsyncIterator[AsyncSession]:
        async with session_factory() as session:
            yield session

    app.dependency_overrides[get_db_session] = override_db_session

    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get("/providers/tushare/readiness")
    finally:
        app.dependency_overrides.clear()
        get_settings.cache_clear()

    assert response.status_code == 200
    payload = response.json()
    assert payload["provider_name"] == "tushare"
    assert payload["status"] == "warning"
    assert payload["token_configured"] is True
    assert payload["scheduler_enabled"] is False
    assert payload["scheduler_ready_endpoint_count"] == 1
    assert "secret-tushare-token" not in response.text

    by_endpoint = {item["endpoint"]: item for item in payload["endpoints"]}
    assert by_endpoint["stock_basic"]["scheduler_eligible"] is True
    assert by_endpoint["stock_basic"]["latest_status"] == "success"
    assert by_endpoint["stock_basic"]["latest_quality_status"] == "ok"
    assert by_endpoint["anns_d"]["status"] == "warning"
