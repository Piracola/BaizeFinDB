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
from app.radar.schemas import RadarSignalModelAnalysisDraftRead
from app.telegram.formatter import (
    format_holdings,
    format_ops_trends,
    format_ops_warning_drilldown,
    format_radar_overview,
    format_reports,
    format_signal_analysis,
    format_signal_detail,
    format_signal_model_analysis_draft,
    format_signals,
    format_watchlist_items,
)


@pytest.fixture(autouse=True)
def telegram_env(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "")
    monkeypatch.setenv("TELEGRAM_ALLOWED_CHAT_IDS", "")
    monkeypatch.setenv("TELEGRAM_WEBHOOK_SECRET", "")
    monkeypatch.setenv("TELEGRAM_REQUIRE_BINDING", "false")
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
    monkeypatch.setenv("TELEGRAM_REQUIRE_BINDING", "true")
    get_settings.cache_clear()

    response = await client.get("/telegram/status")

    assert response.status_code == 200
    assert response.json() == {
        "bot_token_configured": True,
        "allowed_chat_count": 2,
        "binding_count": 0,
        "active_binding_count": 0,
        "require_binding": True,
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
    assert "/ops_history" in data["preview"]
    assert "/ops_trends" in data["preview"]
    assert "/ops_ready" in data["preview"]
    assert "/ops_warn" in data["preview"]
    assert "/tushare" in data["preview"]
    assert "/tushare_ready" in data["preview"]
    assert "/holding" in data["preview"]
    assert "/watchlist" in data["preview"]
    assert "/reports" in data["preview"]
    assert "/daily" in data["preview"]
    assert "/weekly" in data["preview"]
    assert "/analysis <id>" in data["preview"]
    assert "/model_draft <id>" in data["preview"]
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
async def test_telegram_require_binding_rejects_unbound_help_but_allows_id(
    monkeypatch: pytest.MonkeyPatch,
    client: AsyncClient,
) -> None:
    monkeypatch.setenv("TELEGRAM_REQUIRE_BINDING", "true")
    get_settings.cache_clear()

    help_response = await client.post("/telegram/webhook", json=_telegram_update("/help"))
    id_response = await client.post("/telegram/webhook", json=_telegram_update("/id"))

    assert help_response.status_code == 200
    help_data = help_response.json()
    assert help_data["accepted"] is False
    assert help_data["authorized"] is False
    assert help_data["delivery"] == "skipped"
    assert "白名单" in help_data["preview"]

    assert id_response.status_code == 200
    id_data = id_response.json()
    assert id_data["accepted"] is True
    assert id_data["authorized"] is False
    assert "当前聊天 ID：1001" in id_data["preview"]


@pytest.mark.asyncio
async def test_telegram_require_binding_allows_active_binding(
    monkeypatch: pytest.MonkeyPatch,
    client: AsyncClient,
) -> None:
    monkeypatch.setenv("TELEGRAM_REQUIRE_BINDING", "true")
    get_settings.cache_clear()
    await client.post("/telegram/bindings", json={"chat_id": 1001, "is_allowed": True})

    response = await client.post("/telegram/webhook", json=_telegram_update("/help"))

    assert response.status_code == 200
    data = response.json()
    assert data["accepted"] is True
    assert data["authorized"] is True


@pytest.mark.asyncio
@pytest.mark.parametrize("require_binding", ["false", "true"])
async def test_telegram_disabled_binding_rejects_chat(
    monkeypatch: pytest.MonkeyPatch,
    client: AsyncClient,
    require_binding: str,
) -> None:
    monkeypatch.setenv("TELEGRAM_REQUIRE_BINDING", require_binding)
    get_settings.cache_clear()
    await client.post("/telegram/bindings", json={"chat_id": 1001, "is_allowed": False})

    response = await client.post("/telegram/webhook", json=_telegram_update("/help"))

    assert response.status_code == 200
    data = response.json()
    assert data["accepted"] is False
    assert data["authorized"] is False


@pytest.mark.asyncio
async def test_telegram_env_allow_list_still_allows_without_binding_in_strict_mode(
    monkeypatch: pytest.MonkeyPatch,
    client: AsyncClient,
) -> None:
    monkeypatch.setenv("TELEGRAM_ALLOWED_CHAT_IDS", "1001")
    monkeypatch.setenv("TELEGRAM_REQUIRE_BINDING", "true")
    get_settings.cache_clear()

    response = await client.post("/telegram/webhook", json=_telegram_update("/help"))

    assert response.status_code == 200
    data = response.json()
    assert data["accepted"] is True
    assert data["authorized"] is True


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
    monkeypatch: pytest.MonkeyPatch,
    session_factory: async_sessionmaker[AsyncSession],
    client: AsyncClient,
) -> None:
    monkeypatch.setattr("app.ops.service.psutil.cpu_count", lambda logical=True: 8)
    monkeypatch.setattr("app.ops.service.psutil.cpu_percent", lambda interval=None: 18.5)
    monkeypatch.setattr(
        "app.ops.service.psutil.virtual_memory",
        lambda: SimpleNamespace(
            total=16_000_000,
            available=8_000_000,
            used=8_000_000,
            percent=50.0,
        ),
    )
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
    assert "服务端：运行" in preview
    assert "磁盘可用" in preview
    assert "CPU 18.5%" in preview
    assert "内存 50%" in preview
    assert "Provider：异常 0 / 总数 0 / 最新 暂无" in preview
    assert "告警：最近雷达扫描失败率偏高。" in preview
    assert "该视图只读取已有运行记录" in preview
    assert "不构成投资建议" in preview


@pytest.mark.asyncio
async def test_telegram_ops_history_command_reports_recent_events(
    session_factory: async_sessionmaker[AsyncSession],
    client: AsyncClient,
) -> None:
    now = datetime.now(UTC)
    async with session_factory() as session:
        session.add(
            RadarScanBatch(
                status="failure",
                started_at=now - timedelta(minutes=10),
                finished_at=now - timedelta(minutes=9),
                source_snapshot_ids=[],
                summary={"error_type": "ProviderError"},
                error_message="provider down",
            ),
        )
        await session.commit()

    response = await client.post("/telegram/webhook", json=_telegram_update("/ops_history"))

    assert response.status_code == 200
    preview = response.json()["preview"]
    assert "运维历史" in preview
    assert "统计窗口：最近 24 小时" in preview
    assert "异常汇总：雷达 failure=1" in preview
    assert "最近事件：" in preview
    assert "雷达 #" in preview
    assert "异常" in preview
    assert "不构成投资建议" in preview


@pytest.mark.asyncio
async def test_telegram_ops_trends_command_routes_backend_bucket_counts_only(
    monkeypatch: pytest.MonkeyPatch,
    client: AsyncClient,
) -> None:
    calls: list[tuple[int, int]] = []
    now = datetime(2026, 5, 4, 12, 0, tzinfo=UTC)

    async def fake_trends(
        session: AsyncSession,
        *,
        lookback_hours: int,
        bucket_count: int,
    ) -> SimpleNamespace:
        calls.append((lookback_hours, bucket_count))
        return SimpleNamespace(
            lookback_hours=lookback_hours,
            bucket_count=bucket_count,
            bucket_seconds=7200,
            buckets=[
                SimpleNamespace(
                    bucket_index=index,
                    bucket_started_at=now - timedelta(hours=12 - (index * 2)),
                    bucket_finished_at=now - timedelta(hours=10 - (index * 2)),
                    radar_scan_count=index,
                    radar_failure_count=1 if index == 5 else 0,
                    provider_fetch_total_count=index + 1,
                    provider_fetch_unhealthy_count=index % 2,
                    data_quality_total_count=index + 2,
                    data_quality_unhealthy_count=1 if index == 4 else 0,
                    telegram_push_total_count=index + 3,
                    telegram_push_unhealthy_count=1 if index == 5 else 0,
                    model_call_total_count=index + 4,
                    model_call_unhealthy_count=2 if index == 5 else 0,
                )
                for index in range(6)
            ],
        )

    async def forbidden_async(*args: object, **kwargs: object) -> object:
        raise AssertionError("forbidden Telegram /ops_trends side effect")

    def forbidden_sync(*args: object, **kwargs: object) -> object:
        raise AssertionError("forbidden Telegram /ops_trends side effect")

    monkeypatch.setattr("app.telegram.service.get_ops_trends", fake_trends)
    for name in (
        "get_ops_readiness",
        "get_ops_overview",
        "get_ops_history",
        "get_latest_radar_scan",
        "get_radar_overview",
        "get_radar_signal_detail",
        "list_radar_signals",
        "list_holdings",
        "list_watchlist_items",
        "get_tushare_readiness",
        "list_reports",
        "generate_periodic_report",
        "generate_signal_scores",
    ):
        monkeypatch.setattr(f"app.telegram.service.{name}", forbidden_async)
    monkeypatch.setattr("app.telegram.service.get_tushare_provider_status", forbidden_sync)

    response = await client.post("/telegram/webhook", json=_telegram_update("/ops_trends"))

    assert response.status_code == 200
    data = response.json()
    assert data["command"] == "/ops_trends"
    assert data["delivery"] == "preview"
    assert calls == [(24, 12)]
    assert "OPS 趋势摘要" in data["preview"]
    assert "统计窗口：最近 24 小时" in data["preview"]
    assert "时间桶：6/12 个" in data["preview"]
    assert "最新桶：扫描 5 / 失败 1" in data["preview"]
    assert "最新 unhealthy：Provider 1 / 数据质量 0 / 推送 1 / 模型 2" in data["preview"]
    assert "已折叠 1 个更早时间桶" in data["preview"]
    assert "不重算 readiness 或运行状态" in data["preview"]
    assert "不触发采集、扫描、评分、报告、推送、模型调用" in data["preview"]


def test_telegram_ops_trends_formatter_uses_bounded_backend_bucket_counts_only() -> None:
    now = datetime(2026, 5, 4, 12, 0, tzinfo=UTC)
    trends = SimpleNamespace(
        lookback_hours=24,
        bucket_count=12,
        bucket_seconds=7200,
        buckets=[
            SimpleNamespace(
                bucket_index=index,
                bucket_started_at=now - timedelta(hours=12 - (index * 2)),
                bucket_finished_at=now - timedelta(hours=10 - (index * 2)),
                radar_scan_count=index,
                radar_failure_count=index % 3,
                provider_fetch_total_count=10 + index,
                provider_fetch_unhealthy_count=index,
                data_quality_total_count=20 + index,
                data_quality_unhealthy_count=index + 1,
                telegram_push_total_count=30 + index,
                telegram_push_unhealthy_count=index + 2,
                model_call_total_count=40 + index,
                model_call_unhealthy_count=index + 3,
            )
            for index in range(7)
        ],
    )

    preview = format_ops_trends(trends)

    assert "OPS 趋势摘要" in preview
    assert "最新桶：扫描 6 / 失败 0" in preview
    assert "最新 unhealthy：Provider 6 / 数据质量 7 / 推送 8 / 模型 9" in preview
    assert "#2" in preview
    assert "#6" in preview
    assert "#1" not in preview
    assert "已折叠 2 个更早时间桶" in preview
    assert "readiness" in preview
    assert "状态：阻断" not in preview
    assert "告警：" not in preview
    assert "服务端：" not in preview
    assert "不构成投资建议" in preview


@pytest.mark.asyncio
async def test_telegram_ops_ready_command_reports_readiness(client: AsyncClient) -> None:
    response = await client.post("/telegram/webhook", json=_telegram_update("/ops_ready"))

    assert response.status_code == 200
    preview = response.json()["preview"]
    assert "运行就绪自检" in preview
    assert "状态：阻断" in preview
    assert "雷达新鲜度：失败" in preview
    assert "该视图只读取已有运行记录" in preview
    assert "不构成投资建议" in preview


@pytest.mark.asyncio
async def test_telegram_ops_warn_command_routes_read_only_ops_calls(
    monkeypatch: pytest.MonkeyPatch,
    client: AsyncClient,
) -> None:
    calls: list[tuple[str, int, int | None]] = []
    now = datetime(2026, 5, 4, 12, 0, tzinfo=UTC)

    async def fake_readiness(session: AsyncSession, *, lookback_hours: int) -> SimpleNamespace:
        calls.append(("readiness", lookback_hours, None))
        return SimpleNamespace(
            status="warning",
            lookback_hours=lookback_hours,
            checks=[
                SimpleNamespace(name="server_disk", status="ok", message="服务端磁盘空间充足。"),
                SimpleNamespace(
                    name="provider_fetch",
                    status="warning",
                    message="Provider 存在异常记录。",
                ),
            ],
        )

    async def fake_overview(session: AsyncSession, *, lookback_hours: int) -> SimpleNamespace:
        calls.append(("overview", lookback_hours, None))
        return SimpleNamespace(
            alerts=[
                SimpleNamespace(
                    severity="warning",
                    code="provider_fetch_unhealthy",
                    message="Provider 拉取存在 2 条异常记录。",
                ),
            ],
        )

    async def fake_history(
        session: AsyncSession,
        *,
        lookback_hours: int,
        limit: int,
    ) -> SimpleNamespace:
        calls.append(("history", lookback_hours, limit))
        return SimpleNamespace(
            failure_summary=[
                SimpleNamespace(kind="provider_fetch", key="akshare/news/failure", count=2),
            ],
            recent_events=[
                SimpleNamespace(
                    id=1,
                    kind="provider_fetch",
                    status="failure",
                    occurred_at=now,
                    detail="provider down",
                ),
            ],
        )

    async def forbidden_async(*args: object, **kwargs: object) -> object:
        raise AssertionError("forbidden Telegram /ops_warn side effect")

    def forbidden_sync(*args: object, **kwargs: object) -> object:
        raise AssertionError("forbidden Telegram /ops_warn side effect")

    monkeypatch.setattr("app.telegram.service.get_ops_readiness", fake_readiness)
    monkeypatch.setattr("app.telegram.service.get_ops_overview", fake_overview)
    monkeypatch.setattr("app.telegram.service.get_ops_history", fake_history)
    for name in (
        "get_latest_radar_scan",
        "get_radar_overview",
        "get_radar_signal_detail",
        "list_radar_signals",
        "list_holdings",
        "list_watchlist_items",
        "get_tushare_readiness",
        "list_reports",
        "generate_periodic_report",
        "generate_signal_scores",
    ):
        monkeypatch.setattr(f"app.telegram.service.{name}", forbidden_async)
    monkeypatch.setattr("app.telegram.service.get_tushare_provider_status", forbidden_sync)

    response = await client.post("/telegram/webhook", json=_telegram_update("/ops_warn"))

    assert response.status_code == 200
    data = response.json()
    assert data["command"] == "/ops_warn"
    assert data["delivery"] == "preview"
    assert calls == [
        ("readiness", 24, None),
        ("overview", 24, None),
        ("history", 24, 10),
    ]
    assert "OPS 告警钻取" in data["preview"]
    assert "非 OK 自检" in data["preview"]
    assert "Provider：警告" in data["preview"]
    assert "告警：" in data["preview"]
    assert "异常汇总：" in data["preview"]
    assert "最近事件：" in data["preview"]
    assert "不触发采集、扫描、评分、报告、推送、模型调用" in data["preview"]


def test_telegram_ops_warn_formatter_prioritizes_backend_warning_fields() -> None:
    now = datetime(2026, 5, 4, 12, 0, tzinfo=UTC)
    readiness = SimpleNamespace(
        status="blocked",
        lookback_hours=24,
        checks=[
            SimpleNamespace(name="server_disk", status="ok", message="服务端磁盘空间充足。"),
            SimpleNamespace(
                name="provider_fetch",
                status="fail",
                message="Provider 最近记录全部异常。",
            ),
            SimpleNamespace(
                name="data_quality",
                status="warning",
                message="数据质量存在异常记录。",
            ),
        ],
    )
    overview = SimpleNamespace(
        alerts=[
            SimpleNamespace(
                severity="warning",
                code="provider_fetch_unhealthy",
                message="Provider 异常。",
            ),
            SimpleNamespace(
                severity="warning",
                code="data_quality_unhealthy",
                message="数据质量异常。",
            ),
        ],
    )
    history = SimpleNamespace(
        failure_summary=[
            SimpleNamespace(kind="provider_fetch", key="akshare/news/failure", count=3),
            SimpleNamespace(kind="data_quality", key="akshare/news/degraded", count=2),
        ],
        recent_events=[
            SimpleNamespace(
                id=index,
                kind="provider_fetch",
                status="failure",
                occurred_at=now - timedelta(minutes=index),
                detail=f"event {index}",
            )
            for index in range(1, 8)
        ],
    )

    preview = format_ops_warning_drilldown(
        readiness=readiness,
        overview=overview,
        history=history,
    )

    assert preview.index("状态：阻断") < preview.index("非 OK 自检：")
    assert preview.index("非 OK 自检：") < preview.index("告警：")
    assert preview.index("告警：") < preview.index("异常汇总：")
    assert preview.index("异常汇总：") < preview.index("最近事件：")
    assert "服务端磁盘" not in preview
    assert "Provider：失败" in preview
    assert "数据质量：警告" in preview
    assert "provider_fetch_unhealthy" in preview
    assert "Provider akshare/news/failure=3" in preview
    assert "event 5" in preview
    assert "event 6" not in preview
    assert "不触发采集、扫描、评分、报告、推送、模型调用" in preview


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
    assert "已实现端点：4/4" in preview
    assert "不触发真实抓取" in preview
    assert "不构成投资建议" in preview
    assert "real-tushare-token" not in preview


@pytest.mark.asyncio
async def test_telegram_tushare_ready_command_reports_read_only_readiness(
    monkeypatch: pytest.MonkeyPatch,
    client: AsyncClient,
) -> None:
    monkeypatch.setenv("TUSHARE_TOKEN", "real-tushare-token")
    get_settings.cache_clear()

    response = await client.post("/telegram/webhook", json=_telegram_update("/tushare_ready"))

    assert response.status_code == 200
    preview = response.json()["preview"]
    assert "Tushare 准入自检" in preview
    assert "Token：已配置" in preview
    assert "调度准入样例：0/4" in preview
    assert "不触发真实抓取或调度" in preview
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
    analysis_response = await client.post(
        "/telegram/webhook",
        json=_telegram_update(f"/analysis {signal_id}"),
    )
    invalid_analysis_response = await client.post(
        "/telegram/webhook",
        json=_telegram_update("/analysis not-a-number"),
    )
    missing_analysis_response = await client.post(
        "/telegram/webhook",
        json=_telegram_update("/analysis 999999"),
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

    assert analysis_response.status_code == 200
    analysis_preview = analysis_response.json()["preview"]
    assert f"信号 #{signal_id} 分析摘要" in analysis_preview
    assert "标题：P1 research brief: AI Applications" in analysis_preview
    assert "指标摘要" in analysis_preview
    assert "Agent 评估" in analysis_preview
    assert "证据摘要" in analysis_preview
    assert "审查摘要" in analysis_preview
    assert "后续动作" in analysis_preview
    assert "不在 Telegram 层计算雷达定级" in analysis_preview
    assert "raw_excerpt" not in analysis_preview
    assert "source_ref" not in analysis_preview
    assert "internal raw excerpt" not in analysis_preview

    assert invalid_analysis_response.status_code == 200
    assert "请使用 /analysis <id>" in invalid_analysis_response.json()["preview"]

    assert missing_analysis_response.status_code == 200
    assert "未找到 #999999 信号" in missing_analysis_response.json()["preview"]


@pytest.mark.asyncio
async def test_telegram_model_draft_command_is_manual_and_default_disabled(
    session_factory: async_sessionmaker[AsyncSession],
    client: AsyncClient,
) -> None:
    signal_id = await _seed_signal(session_factory)

    model_draft_response = await client.post(
        "/telegram/webhook",
        json=_telegram_update(f"/model_draft {signal_id}"),
    )
    invalid_model_draft_response = await client.post(
        "/telegram/webhook",
        json=_telegram_update("/model_draft not-a-number"),
    )
    missing_argument_model_draft_response = await client.post(
        "/telegram/webhook",
        json=_telegram_update("/model_draft"),
    )
    missing_model_draft_response = await client.post(
        "/telegram/webhook",
        json=_telegram_update("/model_draft 999999"),
    )

    assert model_draft_response.status_code == 200
    preview = model_draft_response.json()["preview"]
    assert f"信号 #{signal_id} 模型草稿" in preview
    assert "模型状态：未启用 (disabled)" in preview
    assert "草稿状态：不可用 (not_available)" in preview
    assert "模型分析未启用或 Provider 未配置" in preview
    assert "阻断词数量：0" in preview
    assert "不在 Telegram 层计算模型状态" in preview
    assert "raw_prompt" not in preview
    assert "response_excerpt" not in preview
    assert "source_ref" not in preview
    assert "raw_excerpt" not in preview

    assert invalid_model_draft_response.status_code == 200
    assert "请使用 /model_draft <id>" in invalid_model_draft_response.json()["preview"]

    assert missing_argument_model_draft_response.status_code == 200
    assert (
        "请使用 /model_draft <id>" in missing_argument_model_draft_response.json()["preview"]
    )

    assert missing_model_draft_response.status_code == 200
    assert "未找到 #999999 信号" in missing_model_draft_response.json()["preview"]


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
    analysis_preview = format_signal_analysis(
        SimpleNamespace(
            signal_id=7,
            subject_name="AI Applications",
            priority="P1",
            lifecycle_stage="developing",
            review_status="needs_human_review",
            analysis_title="P1 research brief: AI Applications",
            key_points=[
                "Backend priority is P1; lifecycle is developing.",
                "Review status requires human review.",
            ],
            metric_highlights=[
                SimpleNamespace(
                    label="sector_pct_change",
                    value="+3.4%",
                    interpretation="Sector momentum is above the watch threshold.",
                ),
            ],
            risk_flags=["provider_quality_degraded", "low_evidence_confidence"],
            evidence_summary=SimpleNamespace(
                evidence_count=1,
                evidence_types=["market_snapshot"],
                summaries=[
                    "Provider snapshot summary from [source omitted] with sector movement."
                ],
                freshness_labels=["fresh"],
                confidence_labels=["low", "0.123"],
                source_ref="https://example.com/raw",
                raw_excerpt="Raw source says buy now",
            ),
            review_summary=SimpleNamespace(
                status="needs_human_review",
                latest_review_id=4,
                reasons=["low evidence confidence"],
                human_review_required=True,
                details={"cost_price": 10.25, "position_ratio": 0.2},
            ),
            agent_assessments=[
                SimpleNamespace(
                    agent_id="data_quality_agent",
                    label="Data Quality Agent",
                    status="warning",
                    summary="Confidence bucket needs review.",
                    findings=["Confidence bucket: low.", "source_ref: https://example.com"],
                    next_actions=["Refresh provider snapshots."],
                ),
                SimpleNamespace(
                    agent_id="risk_agent",
                    label="Risk Agent",
                    status="warning",
                    summary="Raw note says buy now.",
                    findings=["position_ratio: 0.2"],
                    next_actions=["Keep output framed as research review."],
                ),
            ],
            agent_inputs=SimpleNamespace(
                guardrails=["Do not override backend rule priority"],
            ),
            next_actions=["Schedule human review before publishing."],
            raw_excerpt="sell immediately",
        ),
    )
    model_draft_preview = format_signal_model_analysis_draft(
        RadarSignalModelAnalysisDraftRead(
            signal_id=7,
            model_status="fallback",
            draft_status="ok",
            provider="openai",
            model="fallback-model",
            fallback_model="fallback-model",
            audit_log_id=12,
            advisory_summary="模型草稿摘要，参考 [source omitted]。",
            observations=[
                "Backend model draft uses sanitized deterministic analysis.",
                "source_ref: https://example.com/raw",
            ],
            risk_notes=["Raw note says buy now."],
            follow_up_questions=["Check whether provider quality recovered."],
            suggested_attention_label="继续观察",
            blocked_terms=["马上买入", "sell"],
            boundary="Manual opt-in model draft; does not change backend state.",
        ),
    )
    overview_preview = format_radar_overview(overview)
    holdings_preview = format_holdings([])
    watchlist_preview = format_watchlist_items([])
    reports_preview = format_reports([])

    assert "生命周期：发展观察" in signals_preview
    assert "审查：候选待审" in signals_preview
    assert "生命周期：发展观察" in signal_preview
    assert "审查状态：候选待审" in signal_preview
    assert "信号 #7 分析摘要" in analysis_preview
    assert "优先级：P1" in analysis_preview
    assert "生命周期：发展观察" in analysis_preview
    assert "审查状态：需要人工复核" in analysis_preview
    assert "sector_pct_change: +3.4%" in analysis_preview
    assert "provider_quality_degraded" in analysis_preview
    assert "Agent 评估" in analysis_preview
    assert "Data Quality Agent（data_quality_agent / warning）" in analysis_preview
    assert "Confidence bucket: low." in analysis_preview
    assert "Refresh provider snapshots." in analysis_preview
    assert "信心分桶：low" in analysis_preview
    assert "0.123" not in analysis_preview
    assert "source_ref" not in analysis_preview
    assert "raw_excerpt" not in analysis_preview
    assert "https://example.com" not in analysis_preview
    assert "cost_price" not in analysis_preview
    assert "position_ratio" not in analysis_preview
    assert "buy" not in analysis_preview.lower()
    assert "sell" not in analysis_preview.lower()
    assert "买入" not in analysis_preview
    assert "卖出" not in analysis_preview
    assert "信号 #7 模型草稿" in model_draft_preview
    assert "模型状态：已使用备用模型 (fallback)" in model_draft_preview
    assert "草稿状态：已生成 (ok)" in model_draft_preview
    assert "Provider：openai" in model_draft_preview
    assert "Fallback Model：fallback-model" in model_draft_preview
    assert "Audit Log：#12" in model_draft_preview
    assert "模型草稿摘要" in model_draft_preview
    assert "Backend model draft uses sanitized deterministic analysis." in model_draft_preview
    assert "Check whether provider quality recovered." in model_draft_preview
    assert "继续观察" in model_draft_preview
    assert "阻断词数量：2" in model_draft_preview
    assert "不在 Telegram 层计算模型状态" in model_draft_preview
    assert "source_ref" not in model_draft_preview
    assert "raw_excerpt" not in model_draft_preview
    assert "https://example.com" not in model_draft_preview
    assert "cost_price" not in model_draft_preview
    assert "position_ratio" not in model_draft_preview
    assert "buy" not in model_draft_preview.lower()
    assert "sell" not in model_draft_preview.lower()
    assert "马上买入" not in model_draft_preview
    assert "买入" not in model_draft_preview
    assert "卖出" not in model_draft_preview
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
