from collections.abc import AsyncIterator

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.db.base import Base
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
async def test_portfolio_holding_crud_and_user_isolation(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    app = create_app()

    async def override_db_session() -> AsyncIterator[AsyncSession]:
        async with session_factory() as session:
            yield session

    app.dependency_overrides[get_db_session] = override_db_session

    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            create_response = await client.post(
                "/portfolio/holdings",
                json={
                    "instrument_code": " 600000 ",
                    "instrument_name": "浦发银行",
                    "market": "a_share",
                    "note": "核心观察仓",
                    "cost_price": 10.25,
                    "position_ratio": 0.2,
                    "alert_enabled": True,
                },
            )
            duplicate_response = await client.post(
                "/portfolio/holdings",
                json={
                    "instrument_code": "600000",
                    "instrument_name": "浦发银行",
                    "market": "A_SHARE",
                },
            )
            default_list_response = await client.get("/portfolio/holdings")
            other_list_response = await client.get(
                "/portfolio/holdings",
                params={"user_key": "other"},
            )
            holding_id = create_response.json()["id"]
            update_response = await client.patch(
                f"/portfolio/holdings/{holding_id}",
                json={"note": "降低提醒频率", "alert_enabled": False},
            )
            cross_user_delete_response = await client.delete(
                f"/portfolio/holdings/{holding_id}",
                params={"user_key": "other"},
            )
            delete_response = await client.delete(f"/portfolio/holdings/{holding_id}")
            missing_response = await client.patch(
                f"/portfolio/holdings/{holding_id}",
                json={"note": "deleted"},
            )
    finally:
        app.dependency_overrides.clear()

    assert create_response.status_code == 201
    created = create_response.json()
    assert created["user_key"] == "default"
    assert created["instrument_code"] == "600000"
    assert created["market"] == "A_SHARE"
    assert created["cost_price"] == 10.25
    assert created["position_ratio"] == 0.2

    assert duplicate_response.status_code == 409
    assert default_list_response.status_code == 200
    assert len(default_list_response.json()) == 1
    assert other_list_response.status_code == 200
    assert other_list_response.json() == []

    assert update_response.status_code == 200
    assert update_response.json()["note"] == "降低提醒频率"
    assert update_response.json()["alert_enabled"] is False

    assert cross_user_delete_response.status_code == 404
    assert delete_response.status_code == 204
    assert missing_response.status_code == 404


@pytest.mark.asyncio
async def test_watchlist_crud(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    app = create_app()

    async def override_db_session() -> AsyncIterator[AsyncSession]:
        async with session_factory() as session:
            yield session

    app.dependency_overrides[get_db_session] = override_db_session

    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            create_response = await client.post(
                "/portfolio/watchlist",
                params={"user_key": "telegram-1001"},
                json={
                    "instrument_code": "sz000001",
                    "instrument_name": "平安银行",
                    "market": "a_share",
                    "note": "观察风险变化",
                },
            )
            duplicate_response = await client.post(
                "/portfolio/watchlist",
                params={"user_key": "telegram-1001"},
                json={
                    "instrument_code": "SZ000001",
                    "instrument_name": "平安银行",
                    "market": "A_SHARE",
                },
            )
            list_response = await client.get(
                "/portfolio/watchlist",
                params={"user_key": "telegram-1001"},
            )
            item_id = create_response.json()["id"]
            update_response = await client.patch(
                f"/portfolio/watchlist/{item_id}",
                params={"user_key": "telegram-1001"},
                json={"alert_enabled": False},
            )
            delete_response = await client.delete(
                f"/portfolio/watchlist/{item_id}",
                params={"user_key": "telegram-1001"},
            )
    finally:
        app.dependency_overrides.clear()

    assert create_response.status_code == 201
    created = create_response.json()
    assert created["user_key"] == "telegram-1001"
    assert created["instrument_code"] == "SZ000001"
    assert created["market"] == "A_SHARE"

    assert duplicate_response.status_code == 409
    assert list_response.status_code == 200
    assert len(list_response.json()) == 1
    assert update_response.status_code == 200
    assert update_response.json()["alert_enabled"] is False
    assert delete_response.status_code == 204
