from collections.abc import AsyncIterator, Iterator
from datetime import UTC, datetime

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


@pytest.fixture(autouse=True)
def telegram_push_env(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "")
    monkeypatch.setenv("TELEGRAM_ALLOWED_CHAT_IDS", "")
    monkeypatch.setenv("TELEGRAM_WEBHOOK_SECRET", "")
    monkeypatch.setenv("TELEGRAM_REQUIRE_BINDING", "false")
    monkeypatch.setenv("TELEGRAM_PUSH_ENABLED", "false")
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
async def test_telegram_push_latest_filters_reviews_logs_and_dedupes(
    session_factory: async_sessionmaker[AsyncSession],
    client: AsyncClient,
) -> None:
    approved_id, blocked_id, human_review_id = await _seed_push_scan(session_factory)

    response = await client.post(
        "/telegram/push/latest",
        json={"chat_ids": [1001], "dry_run": False},
    )
    duplicate_response = await client.post(
        "/telegram/push/latest",
        json={"chat_ids": [1001], "dry_run": False},
    )
    logs_response = await client.get(
        "/telegram/push/logs",
        params={"user_key": "telegram-1001"},
    )

    assert response.status_code == 200
    data = response.json()
    assert data["source_scan_id"] is not None
    assert data["recipient_count"] == 1
    assert data["included_signal_ids"] == [human_review_id, approved_id]
    assert data["blocked_signal_ids"] == [blocked_id]
    assert data["needs_human_review_signal_ids"] == [human_review_id]
    assert data["priority_counts"] == {"P0": 0, "P1": 1, "P2": 1}

    delivery = data["deliveries"][0]
    assert delivery["delivery"] == "preview"
    assert delivery["sent"] is False
    assert delivery["push_log_id"] is not None
    assert "雷达折叠推送" in delivery["preview"]
    assert "P1：1 条" in delivery["preview"]
    assert "P2：1 条" in delivery["preview"]
    assert "需人工复核" in delivery["preview"]
    assert "已过滤 1 条审查阻断信号" in delivery["preview"]
    assert "internal raw excerpt" not in delivery["preview"]
    for forbidden in ("买入", "卖出", "满仓", "稳赚", "保证收益"):
        assert forbidden not in delivery["preview"]

    assert duplicate_response.status_code == 200
    duplicate_delivery = duplicate_response.json()["deliveries"][0]
    assert duplicate_delivery["delivery"] == "skipped"
    assert duplicate_delivery["push_log_id"] == delivery["push_log_id"]
    assert duplicate_delivery["error"] == "duplicate_radar_scan_push"

    assert logs_response.status_code == 200
    logs = logs_response.json()
    assert len(logs) == 1
    assert logs[0]["status"] == "preview"
    assert logs[0]["included_signal_ids"] == [human_review_id, approved_id]
    assert logs[0]["blocked_signal_ids"] == [blocked_id]
    assert logs[0]["needs_human_review_signal_ids"] == [human_review_id]
    assert "internal raw excerpt" not in logs[0]["message_text"]


@pytest.mark.asyncio
async def test_telegram_push_dry_run_does_not_write_log(
    session_factory: async_sessionmaker[AsyncSession],
    client: AsyncClient,
) -> None:
    await _seed_push_scan(session_factory)

    response = await client.post(
        "/telegram/push/latest",
        json={"chat_ids": [1001], "dry_run": True},
    )
    logs_response = await client.get(
        "/telegram/push/logs",
        params={"user_key": "telegram-1001"},
    )

    assert response.status_code == 200
    delivery = response.json()["deliveries"][0]
    assert delivery["delivery"] == "preview"
    assert delivery["push_log_id"] is None
    assert logs_response.status_code == 200
    assert logs_response.json() == []


@pytest.mark.asyncio
async def test_telegram_push_secret_is_required_when_configured(
    monkeypatch: pytest.MonkeyPatch,
    client: AsyncClient,
) -> None:
    monkeypatch.setenv("TELEGRAM_WEBHOOK_SECRET", "hook-secret")
    get_settings.cache_clear()

    forbidden_response = await client.post(
        "/telegram/push/latest",
        json={"chat_ids": [1001], "dry_run": True},
    )
    allowed_response = await client.post(
        "/telegram/push/latest",
        headers={"X-Telegram-Bot-Api-Secret-Token": "hook-secret"},
        json={"chat_ids": [1001], "dry_run": True},
    )

    assert forbidden_response.status_code == 403
    assert allowed_response.status_code == 200


@pytest.mark.asyncio
async def test_telegram_push_request_chat_ids_respect_whitelist(
    monkeypatch: pytest.MonkeyPatch,
    session_factory: async_sessionmaker[AsyncSession],
    client: AsyncClient,
) -> None:
    monkeypatch.setenv("TELEGRAM_ALLOWED_CHAT_IDS", "1001")
    get_settings.cache_clear()
    await _seed_push_scan(session_factory)

    response = await client.post(
        "/telegram/push/latest",
        json={"chat_ids": [1001, 9999], "dry_run": True},
    )

    assert response.status_code == 200
    data = response.json()
    assert data["recipient_count"] == 1
    assert [delivery["chat_id"] for delivery in data["deliveries"]] == [1001]


@pytest.mark.asyncio
async def test_telegram_push_request_chat_ids_respect_db_bindings(
    session_factory: async_sessionmaker[AsyncSession],
    client: AsyncClient,
) -> None:
    await _seed_push_scan(session_factory)
    await client.post(
        "/telegram/bindings",
        json={"chat_id": 1001, "is_allowed": True},
    )
    await client.post(
        "/telegram/bindings",
        json={"chat_id": 9999, "is_allowed": False},
    )

    response = await client.post(
        "/telegram/push/latest",
        json={"chat_ids": [1001, 2002, 9999], "dry_run": True},
    )

    assert response.status_code == 200
    data = response.json()
    assert data["recipient_count"] == 1
    assert [delivery["chat_id"] for delivery in data["deliveries"]] == [1001]


@pytest.mark.asyncio
async def test_telegram_push_strict_mode_has_no_implicit_recipients_without_bindings(
    monkeypatch: pytest.MonkeyPatch,
    session_factory: async_sessionmaker[AsyncSession],
    client: AsyncClient,
) -> None:
    monkeypatch.setenv("TELEGRAM_REQUIRE_BINDING", "true")
    get_settings.cache_clear()
    await _seed_push_scan(session_factory)

    response = await client.post(
        "/telegram/push/latest",
        json={"dry_run": True},
    )

    assert response.status_code == 200
    data = response.json()
    assert data["recipient_count"] == 0
    assert data["deliveries"] == []


@pytest.mark.asyncio
async def test_telegram_push_generates_standard_report_for_p0(
    session_factory: async_sessionmaker[AsyncSession],
    client: AsyncClient,
) -> None:
    signal_id = await _seed_p0_push_scan(session_factory)

    response = await client.post(
        "/telegram/push/latest",
        json={"chat_ids": [1001], "dry_run": False},
    )
    duplicate_response = await client.post(
        "/telegram/push/latest",
        json={"chat_ids": [1001], "dry_run": False},
    )
    reports_response = await client.get(
        "/reports",
        params={"user_key": "telegram-1001", "report_type": "standard"},
    )

    assert response.status_code == 200
    delivery = response.json()["deliveries"][0]
    assert delivery["delivery"] == "preview"
    assert len(delivery["generated_report_ids"]) == 1

    assert reports_response.status_code == 200
    reports = reports_response.json()
    assert len(reports) == 1
    assert reports[0]["id"] == delivery["generated_report_ids"][0]
    assert reports[0]["signal_id"] == signal_id
    assert reports[0]["report_type"] == "standard"
    assert reports[0]["suggestion_label"] == "重点关注"
    assert reports[0]["details"]["generation_trigger"] == "telegram_p0_push"

    duplicate_delivery = duplicate_response.json()["deliveries"][0]
    assert duplicate_delivery["delivery"] == "skipped"
    assert duplicate_delivery["generated_report_ids"] == []


async def _seed_push_scan(
    session_factory: async_sessionmaker[AsyncSession],
) -> tuple[int, int, int]:
    now = datetime.now(UTC)
    async with session_factory() as session:
        scan = RadarScanBatch(
            status="success",
            started_at=now,
            finished_at=now,
            source_snapshot_ids=[],
            summary={"priority_counts": {"P0": 1, "P1": 1, "P2": 1}},
        )
        session.add(scan)
        await session.flush()

        approved = _signal(
            batch_id=scan.id,
            signal_key="akshare:test:approved",
            subject_name="AI Applications",
            priority="P1",
            lifecycle_stage="developing",
            evidence_count=1,
        )
        blocked = _signal(
            batch_id=scan.id,
            signal_key="akshare:test:blocked",
            subject_name="Missing Evidence Theme",
            priority="P0",
            lifecycle_stage="ignition",
            evidence_count=1,
        )
        human_review = _signal(
            batch_id=scan.id,
            signal_key="akshare:test:human-review",
            subject_name="Low Confidence Theme",
            priority="P2",
            lifecycle_stage="divergence",
            evidence_count=1,
        )
        session.add_all([approved, blocked, human_review])
        await session.flush()

        session.add(
            _evidence(
                signal_id=approved.id,
                collected_at=now,
                confidence=0.8,
            ),
        )
        session.add(
            _evidence(
                signal_id=human_review.id,
                collected_at=now,
                confidence=0.2,
            ),
        )
        await session.commit()
        return approved.id, blocked.id, human_review.id


async def _seed_p0_push_scan(
    session_factory: async_sessionmaker[AsyncSession],
) -> int:
    now = datetime.now(UTC)
    async with session_factory() as session:
        scan = RadarScanBatch(
            status="success",
            started_at=now,
            finished_at=now,
            source_snapshot_ids=[],
            summary={"priority_counts": {"P0": 1, "P1": 0, "P2": 0}},
        )
        session.add(scan)
        await session.flush()

        p0_signal = _signal(
            batch_id=scan.id,
            signal_key="akshare:test:p0-approved",
            subject_name="Mainline Theme",
            priority="P0",
            lifecycle_stage="developing",
            evidence_count=1,
        )
        session.add(p0_signal)
        await session.flush()
        session.add(
            _evidence(
                signal_id=p0_signal.id,
                collected_at=now,
                confidence=0.9,
            ),
        )
        await session.commit()
        return p0_signal.id


def _signal(
    batch_id: int,
    signal_key: str,
    subject_name: str,
    priority: str,
    lifecycle_stage: str,
    evidence_count: int,
) -> RadarSignal:
    return RadarSignal(
        batch_id=batch_id,
        signal_key=signal_key,
        subject_type="sector_concept",
        subject_code=None,
        subject_name=subject_name,
        priority=priority,
        lifecycle_stage=lifecycle_stage,
        review_status="candidate",
        title=f"{priority} radar candidate: {subject_name}",
        summary="Used for folded Telegram push tests.",
        metrics={"pct_change": 3.2},
        evidence_count=evidence_count,
    )


def _evidence(
    signal_id: int,
    collected_at: datetime,
    confidence: float,
) -> SignalEvidence:
    return SignalEvidence(
        signal_id=signal_id,
        evidence_type="market_snapshot",
        source_name="akshare",
        source_ref="market_snapshot:1",
        source_time=None,
        collected_at=collected_at,
        raw_excerpt="internal raw excerpt",
        normalized_summary="provider snapshot summary",
        confidence=confidence,
        freshness="snapshot_latest",
        details={"endpoint": "stock_board_concept_name_em"},
        public_share_policy="internal_summary_only",
    )
