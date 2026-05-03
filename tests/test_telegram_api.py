from collections.abc import AsyncIterator, Iterator
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.core.config import get_settings
from app.db.base import Base
from app.db.radar_models import RadarScanBatch, RadarSignal, SignalEvidence
from app.db.session import get_db_session
from app.main import create_app
from app.telegram.formatter import (
    format_holdings,
    format_radar_overview,
    format_reports,
    format_signal_detail,
    format_signals,
    format_watchlist_items,
)


@pytest.fixture(autouse=True)
def telegram_env(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "")
    monkeypatch.setenv("TELEGRAM_ALLOWED_CHAT_IDS", "")
    monkeypatch.setenv("TELEGRAM_WEBHOOK_SECRET", "")
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


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


@pytest_asyncio.fixture
async def client(
    session_factory: async_sessionmaker[AsyncSession],
) -> AsyncIterator[AsyncClient]:
    app = create_app()

    async def override_db_session() -> AsyncIterator[AsyncSession]:
        async with session_factory() as session:
            yield session

    app.dependency_overrides[get_db_session] = override_db_session

    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as test_client:
            yield test_client
    finally:
        app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_telegram_status_does_not_leak_secrets(
    monkeypatch: pytest.MonkeyPatch,
    client: AsyncClient,
) -> None:
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "123456:secret-token")
    monkeypatch.setenv("TELEGRAM_ALLOWED_CHAT_IDS", "1001,1002")
    monkeypatch.setenv("TELEGRAM_WEBHOOK_SECRET", "hook-secret")
    get_settings.cache_clear()

    response = await client.get("/telegram/status")

    assert response.status_code == 200
    assert response.json() == {
        "bot_token_configured": True,
        "allowed_chat_count": 2,
        "binding_count": 0,
        "active_binding_count": 0,
        "webhook_secret_enabled": True,
        "push_enabled": False,
    }
    assert "123456:secret-token" not in response.text
    assert "hook-secret" not in response.text


@pytest.mark.asyncio
async def test_telegram_help_command_returns_chinese_preview(client: AsyncClient) -> None:
    response = await client.post("/telegram/webhook", json=_telegram_update("/help"))

    assert response.status_code == 200
    data = response.json()
    assert data["accepted"] is True
    assert data["authorized"] is True
    assert data["delivery"] == "preview"
    assert data["sent"] is False
    assert "可用命令" in data["preview"]
    assert "/id" in data["preview"]
    assert "/ops" in data["preview"]
    assert "/tushare" in data["preview"]
    assert "/holding" in data["preview"]
    assert "/watchlist" in data["preview"]
    assert "/reports" in data["preview"]
    assert "/daily" in data["preview"]
    assert "/weekly" in data["preview"]
    assert "/score <id>" in data["preview"]
    assert "不构成投资建议" in data["preview"]
    for forbidden in ("买入", "卖出", "满仓", "稳赚", "保证收益"):
        assert forbidden not in data["preview"]


@pytest.mark.asyncio
async def test_telegram_unauthorized_chat_is_rejected(
    monkeypatch: pytest.MonkeyPatch,
    client: AsyncClient,
) -> None:
    monkeypatch.setenv("TELEGRAM_ALLOWED_CHAT_IDS", "1001,1002")
    get_settings.cache_clear()

    response = await client.post("/telegram/webhook", json=_telegram_update("/help", chat_id=9999))

    assert response.status_code == 200
    data = response.json()
    assert data["accepted"] is False
    assert data["authorized"] is False
    assert data["delivery"] == "skipped"
    assert data["sent"] is False
    assert "白名单" in data["preview"]


@pytest.mark.asyncio
async def test_telegram_id_command_is_available_before_authorization(
    monkeypatch: pytest.MonkeyPatch,
    client: AsyncClient,
) -> None:
    monkeypatch.setenv("TELEGRAM_ALLOWED_CHAT_IDS", "1001")
    get_settings.cache_clear()

    response = await client.post("/telegram/webhook", json=_telegram_update("/id", chat_id=9999))

    assert response.status_code == 200
    data = response.json()
    assert data["accepted"] is True
    assert data["authorized"] is False
    assert data["command"] == "/id"
    assert data["delivery"] == "preview"
    assert "当前聊天 ID：9999" in data["preview"]
    assert "不构成投资建议" in data["preview"]


@pytest.mark.asyncio
async def test_telegram_webhook_secret_is_required_when_configured(
    monkeypatch: pytest.MonkeyPatch,
    client: AsyncClient,
) -> None:
    monkeypatch.setenv("TELEGRAM_WEBHOOK_SECRET", "hook-secret")
    get_settings.cache_clear()

    forbidden_response = await client.post("/telegram/webhook", json=_telegram_update("/help"))
    allowed_response = await client.post(
        "/telegram/webhook",
        headers={"X-Telegram-Bot-Api-Secret-Token": "hook-secret"},
        json=_telegram_update("/help"),
    )

    assert forbidden_response.status_code == 403
    assert allowed_response.status_code == 200


@pytest.mark.asyncio
async def test_telegram_bindings_control_webhook_authorization(client: AsyncClient) -> None:
    create_response = await client.post(
        "/telegram/bindings",
        json={
            "chat_id": 1001,
            "user_key": "telegram-1001",
            "display_name": "primary chat",
            "is_allowed": True,
        },
    )
    status_response = await client.get("/telegram/status")
    list_response = await client.get("/telegram/bindings")
    allowed_response = await client.post("/telegram/webhook", json=_telegram_update("/help"))
    unbound_response = await client.post(
        "/telegram/webhook",
        json=_telegram_update("/help", chat_id=2002),
    )
    disabled_response = await client.patch(
        "/telegram/bindings/1001",
        json={"is_allowed": False},
    )
    blocked_response = await client.post("/telegram/webhook", json=_telegram_update("/help"))

    assert create_response.status_code == 200
    binding = create_response.json()
    assert binding["chat_id"] == 1001
    assert binding["user_key"] == "telegram-1001"
    assert binding["is_allowed"] is True

    assert status_response.status_code == 200
    status_data = status_response.json()
    assert status_data["binding_count"] == 1
    assert status_data["active_binding_count"] == 1

    assert list_response.status_code == 200
    assert list_response.json()[0]["chat_id"] == 1001

    assert allowed_response.status_code == 200
    assert allowed_response.json()["authorized"] is True

    assert unbound_response.status_code == 200
    assert unbound_response.json()["authorized"] is False
    assert "白名单" in unbound_response.json()["preview"]

    assert disabled_response.status_code == 200
    assert disabled_response.json()["is_allowed"] is False

    assert blocked_response.status_code == 200
    assert blocked_response.json()["authorized"] is False


@pytest.mark.asyncio
async def test_telegram_health_command_reports_dependency_status(
    monkeypatch: pytest.MonkeyPatch,
    client: AsyncClient,
) -> None:
    async def ok_check() -> dict[str, str]:
        return {"status": "ok"}

    monkeypatch.setattr("app.telegram.service.check_database", ok_check)
    monkeypatch.setattr("app.telegram.service.check_redis", ok_check)

    response = await client.post("/telegram/webhook", json=_telegram_update("/health"))

    assert response.status_code == 200
    preview = response.json()["preview"]
    assert "健康状态" in preview
    assert "API：正常" in preview
    assert "数据库：正常" in preview
    assert "Redis：正常" in preview
    assert "最近扫描：暂无" in preview


@pytest.mark.asyncio
async def test_telegram_health_command_reports_latest_scan(
    monkeypatch: pytest.MonkeyPatch,
    session_factory: async_sessionmaker[AsyncSession],
    client: AsyncClient,
) -> None:
    async def ok_check() -> dict[str, str]:
        return {"status": "ok"}

    monkeypatch.setattr("app.telegram.service.check_database", ok_check)
    monkeypatch.setattr("app.telegram.service.check_redis", ok_check)
    await _seed_signal(session_factory)

    response = await client.post("/telegram/webhook", json=_telegram_update("/health"))

    assert response.status_code == 200
    preview = response.json()["preview"]
    assert "最近扫描：#" in preview
    assert "完成，信号 1 条" in preview
    assert "开始时间：" in preview


@pytest.mark.asyncio
async def test_telegram_ops_command_reports_runtime_overview(
    session_factory: async_sessionmaker[AsyncSession],
    client: AsyncClient,
) -> None:
    now = datetime.now(UTC)
    async with session_factory() as session:
        session.add_all(
            [
                RadarScanBatch(
                    status="success",
                    started_at=now - timedelta(minutes=5),
                    finished_at=now - timedelta(minutes=4),
                    source_snapshot_ids=[],
                    summary={"signal_count": 1},
                ),
                RadarScanBatch(
                    status="failure",
                    started_at=now - timedelta(minutes=10),
                    finished_at=now - timedelta(minutes=9),
                    source_snapshot_ids=[],
                    summary={"error_type": "ProviderError"},
                    error_message="provider down",
                ),
            ],
        )
        await session.commit()

    response = await client.post("/telegram/webhook", json=_telegram_update("/ops"))

    assert response.status_code == 200
    preview = response.json()["preview"]
    assert "运行状态" in preview
    assert "统计窗口：最近 24 小时" in preview
    assert "雷达扫描：#" in preview
    assert "成功 | 新鲜度：" in preview
    assert "扫描失败率：50% (1/2)" in preview
    assert "Provider：异常 0 / 总数 0 / 最新 暂无" in preview
    assert "该视图只读取已有运行记录" in preview
    assert "不构成投资建议" in preview


@pytest.mark.asyncio
async def test_telegram_tushare_command_reports_read_only_status(
    monkeypatch: pytest.MonkeyPatch,
    client: AsyncClient,
) -> None:
    monkeypatch.setenv("TUSHARE_TOKEN", "real-tushare-token")
    get_settings.cache_clear()

    response = await client.post("/telegram/webhook", json=_telegram_update("/tushare"))

    assert response.status_code == 200
    preview = response.json()["preview"]
    assert "Tushare 状态" in preview
    assert "状态：已配置" in preview
    assert "Token：已配置" in preview
    assert "手动抓取：开启" in preview
    assert "已实现端点：3/3" in preview
    assert "不触发真实抓取" in preview
    assert "不构成投资建议" in preview
    assert "real-tushare-token" not in preview


@pytest.mark.asyncio
async def test_telegram_radar_command_handles_empty_data(client: AsyncClient) -> None:
    response = await client.post("/telegram/webhook", json=_telegram_update("/radar"))

    assert response.status_code == 200
    preview = response.json()["preview"]
    assert "雷达总览" in preview
    assert "P0：0 / P1：0 / P2：0" in preview
    assert "生命周期：暂无" in preview
    assert "个股回推：暂无" in preview
    assert "最新扫描：暂无" in preview


@pytest.mark.asyncio
async def test_telegram_signals_and_signal_detail_commands(
    session_factory: async_sessionmaker[AsyncSession],
    client: AsyncClient,
) -> None:
    signal_id = await _seed_signal(session_factory)

    signals_response = await client.post("/telegram/webhook", json=_telegram_update("/signals"))
    signal_response = await client.post(
        "/telegram/webhook",
        json=_telegram_update(f"/signal {signal_id}"),
    )

    assert signals_response.status_code == 200
    signals_preview = signals_response.json()["preview"]
    assert "最近信号折叠摘要" in signals_preview
    assert f"#{signal_id}" in signals_preview
    assert "AI Applications" in signals_preview

    assert signal_response.status_code == 200
    signal_preview = signal_response.json()["preview"]
    assert f"信号 #{signal_id} 复盘" in signal_preview
    assert "生命周期：发展观察" in signal_preview
    assert "审查状态：候选待审" in signal_preview
    assert "证据数量：1 条" in signal_preview
    assert "证据 1：市场快照" in signal_preview


@pytest.mark.asyncio
async def test_telegram_portfolio_commands_use_chat_user_key(client: AsyncClient) -> None:
    await client.post(
        "/portfolio/holdings",
        params={"user_key": "telegram-1001"},
        json={
            "instrument_code": "600000",
            "instrument_name": "浦发银行",
            "market": "A_SHARE",
            "note": "核心观察仓",
            "cost_price": 10.25,
            "position_ratio": 0.2,
        },
    )
    await client.post(
        "/portfolio/holdings",
        params={"user_key": "telegram-2002"},
        json={
            "instrument_code": "000001",
            "instrument_name": "上证指数",
            "market": "A_SHARE",
        },
    )
    await client.post(
        "/portfolio/watchlist",
        params={"user_key": "telegram-1001"},
        json={
            "instrument_code": "SZ000001",
            "instrument_name": "平安银行",
            "market": "A_SHARE",
            "note": "观察风险变化",
        },
    )

    holding_response = await client.post("/telegram/webhook", json=_telegram_update("/holding"))
    watchlist_response = await client.post("/telegram/webhook", json=_telegram_update("/watchlist"))
    empty_response = await client.post(
        "/telegram/webhook",
        json=_telegram_update("/holding", chat_id=3003),
    )

    assert holding_response.status_code == 200
    holding_preview = holding_response.json()["preview"]
    assert "手动持仓" in holding_preview
    assert "浦发银行" in holding_preview
    assert "仓位：20%" in holding_preview
    assert "上证指数" not in holding_preview

    assert watchlist_response.status_code == 200
    watchlist_preview = watchlist_response.json()["preview"]
    assert "自选关注" in watchlist_preview
    assert "平安银行" in watchlist_preview
    assert "不改变市场雷达等级" in watchlist_preview

    assert empty_response.status_code == 200
    assert "暂未维护持仓" in empty_response.json()["preview"]

    for preview in (holding_preview, watchlist_preview):
        for forbidden in ("买入", "卖出", "满仓", "稳赚", "保证收益"):
            assert forbidden not in preview


@pytest.mark.asyncio
async def test_telegram_reports_command_uses_chat_user_key(
    session_factory: async_sessionmaker[AsyncSession],
    client: AsyncClient,
) -> None:
    signal_id = await _seed_signal(session_factory)
    await client.post(
        "/reports/from-signal",
        params={"user_key": "telegram-1001"},
        json={"signal_id": signal_id, "report_type": "quick"},
    )

    reports_response = await client.post("/telegram/webhook", json=_telegram_update("/reports"))
    empty_response = await client.post(
        "/telegram/webhook",
        json=_telegram_update("/reports", chat_id=2002),
    )

    assert reports_response.status_code == 200
    reports_preview = reports_response.json()["preview"]
    assert "报告列表" in reports_preview
    assert "Quick Report" in reports_preview
    assert "继续观察" in reports_preview
    assert "不构成投资建议" in reports_preview

    assert empty_response.status_code == 200
    assert "暂未生成报告" in empty_response.json()["preview"]


@pytest.mark.asyncio
async def test_telegram_periodic_and_score_commands(
    session_factory: async_sessionmaker[AsyncSession],
    client: AsyncClient,
) -> None:
    signal_id = await _seed_signal(session_factory)

    daily_response = await client.post("/telegram/webhook", json=_telegram_update("/daily"))
    weekly_response = await client.post("/telegram/webhook", json=_telegram_update("/weekly"))
    score_response = await client.post(
        "/telegram/webhook",
        json=_telegram_update(f"/score {signal_id}"),
    )
    invalid_score_response = await client.post(
        "/telegram/webhook",
        json=_telegram_update("/score not-a-number"),
    )

    assert daily_response.status_code == 200
    assert "日报汇总" in daily_response.json()["preview"]
    assert "优先级" in daily_response.json()["preview"]

    assert weekly_response.status_code == 200
    assert "周报汇总" in weekly_response.json()["preview"]

    assert score_response.status_code == 200
    score_preview = score_response.json()["preview"]
    assert f"信号 #{signal_id} 综合评分" in score_preview
    assert "1d" in score_preview
    assert "10d" in score_preview
    assert "窗口未结束 / 观察" in score_preview
    assert "组件：优先级=68.00" in score_preview
    assert "数据质量=50.00" in score_preview
    assert "时效性=90.00" in score_preview
    assert "不是价格回测或交易建议" in score_preview

    assert invalid_score_response.status_code == 200
    assert "请使用 /score <id>" in invalid_score_response.json()["preview"]

    for preview in (
        daily_response.json()["preview"],
        weekly_response.json()["preview"],
        score_preview,
    ):
        for forbidden in ("买入", "卖出", "满仓", "稳赚", "保证收益"):
            assert forbidden not in preview


def test_telegram_formatter_accepts_enum_value_strings() -> None:
    signal = SimpleNamespace(
        id=7,
        priority="P1",
        subject_name="AI Applications",
        lifecycle_stage="developing",
        review_status="candidate",
        evidences=[
            SimpleNamespace(
                evidence_type="market_snapshot",
                source_name="akshare",
                freshness="snapshot_latest",
            ),
        ],
    )
    overview = SimpleNamespace(
        priority_counts={"P0": 0, "P1": 1, "P2": 0},
        lifecycle_counts={"developing": 1},
        stock_backtrace_evidences=[
            {
                "stock_name": "Example AI",
                "stock_pct_change": 7.5,
                "subject_name": "AI Applications",
            }
        ],
        subject_count=1,
        latest_scan=SimpleNamespace(
            id=3,
            status="success",
            signals=[signal],
            started_at=datetime(2026, 5, 3, 9, 30, tzinfo=UTC),
            summary={
                "market_sentiment": {
                    "limit_up_count": 12,
                    "limit_down_count": 2,
                    "broken_limit_up_count": 3,
                    "net_limit_pressure": 7,
                    "sentiment_bias": "positive",
                },
            },
        ),
    )

    signals_preview = format_signals([signal])
    signal_preview = format_signal_detail(signal)
    overview_preview = format_radar_overview(overview)
    holdings_preview = format_holdings([])
    watchlist_preview = format_watchlist_items([])
    reports_preview = format_reports([])

    assert "生命周期：发展观察" in signals_preview
    assert "审查：候选待审" in signals_preview
    assert "生命周期：发展观察" in signal_preview
    assert "审查状态：候选待审" in signal_preview
    assert "最新扫描：#3 完成" in overview_preview
    assert "生命周期：发展观察 1" in overview_preview
    assert "市场情绪：涨停 12 / 跌停 2 / 炸板 3 / 净压力 7 / 偏向：偏强" in overview_preview
    assert "个股回推：Example AI +7.5% -> AI Applications" in overview_preview
    assert "暂未维护持仓" in holdings_preview
    assert "暂未维护自选" in watchlist_preview
    assert "暂未生成报告" in reports_preview


def _telegram_update(text: str, chat_id: int = 1001) -> dict[str, object]:
    return {
        "update_id": 1,
        "message": {
            "message_id": 10,
            "chat": {"id": chat_id},
            "text": text,
        },
    }


async def _seed_signal(session_factory: async_sessionmaker[AsyncSession]) -> int:
    now = datetime.now(UTC)
    async with session_factory() as session:
        scan = RadarScanBatch(
            status="success",
            started_at=now,
            finished_at=now,
            source_snapshot_ids=[],
            summary={"priority_counts": {"P0": 0, "P1": 1, "P2": 0}},
        )
        session.add(scan)
        await session.flush()

        signal = RadarSignal(
            batch_id=scan.id,
            signal_key="akshare:test:AI Applications",
            subject_type="sector_concept",
            subject_code="GN001",
            subject_name="AI Applications",
            priority="P1",
            lifecycle_stage="developing",
            review_status="candidate",
            title="P1 radar candidate",
            summary="Ignored by Telegram formatter.",
            metrics={"pct_change": 3.2},
            evidence_count=1,
        )
        session.add(signal)
        await session.flush()

        session.add(
            SignalEvidence(
                signal_id=signal.id,
                evidence_type="market_snapshot",
                source_name="akshare",
                source_ref="market_snapshot:1",
                source_time=None,
                collected_at=now,
                raw_excerpt="internal raw excerpt",
                normalized_summary="provider snapshot summary",
                confidence=0.8,
                freshness="snapshot_latest",
                details={"endpoint": "stock_board_concept_name_em"},
                public_share_policy="internal_summary_only",
            ),
        )
        await session.commit()
        return signal.id
