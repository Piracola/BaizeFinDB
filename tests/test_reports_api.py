from collections.abc import AsyncIterator
from datetime import UTC, datetime

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.db.base import Base
from app.db.radar_models import RadarScanBatch, RadarSignal, SignalEvidence
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
async def test_report_api_generates_quick_report_from_safe_signal(
    session_factory: async_sessionmaker[AsyncSession],
    client: AsyncClient,
) -> None:
    signal_id = await _seed_signal(session_factory)

    create_response = await client.post(
        "/reports/from-signal",
        json={"signal_id": signal_id, "report_type": "quick"},
    )
    report_id = create_response.json()["id"]
    list_response = await client.get("/reports")
    detail_response = await client.get(f"/reports/{report_id}")
    other_user_response = await client.get(
        f"/reports/{report_id}",
        params={"user_key": "other"},
    )

    assert create_response.status_code == 201
    payload = create_response.json()
    assert payload["report_type"] == "quick"
    assert payload["status"] == "generated"
    assert payload["review_status"] == "approved"
    assert payload["suggestion_label"] == "继续观察"
    assert "不构成投资建议" in payload["body_markdown"]
    assert "internal raw excerpt" not in payload["body_markdown"]
    for forbidden in ("买入", "卖出", "满仓", "稳赚", "保证收益"):
        assert forbidden not in payload["body_markdown"]

    assert list_response.status_code == 200
    assert len(list_response.json()) == 1
    assert detail_response.status_code == 200
    assert detail_response.json()["id"] == report_id
    assert other_user_response.status_code == 404


@pytest.mark.asyncio
async def test_report_api_rejects_deep_report_from_signal(
    session_factory: async_sessionmaker[AsyncSession],
    client: AsyncClient,
) -> None:
    signal_id = await _seed_signal(session_factory)

    response = await client.post(
        "/reports/from-signal",
        json={"signal_id": signal_id, "report_type": "deep"},
    )
    list_response = await client.get("/reports")

    assert response.status_code == 422
    error_text = str(response.json()["detail"])
    assert "report_type" in error_text
    assert "deep" in error_text
    assert list_response.status_code == 200
    assert list_response.json() == []


@pytest.mark.asyncio
async def test_report_api_creates_manual_deep_report_from_signal(
    session_factory: async_sessionmaker[AsyncSession],
    client: AsyncClient,
) -> None:
    signal_id = await _seed_signal(session_factory)

    create_response = await client.post(
        "/reports/deep/from-signal",
        params={"user_key": "research-user"},
        json={"signal_id": signal_id, "confirm_deep_report": True},
    )
    report_id = create_response.json()["id"]
    list_response = await client.get(
        "/reports",
        params={"user_key": "research-user", "report_type": "deep"},
    )
    other_user_response = await client.get(
        f"/reports/{report_id}",
        params={"user_key": "other"},
    )

    assert create_response.status_code == 201
    payload = create_response.json()
    assert payload["report_type"] == "deep"
    assert payload["status"] == "generated"
    assert payload["review_status"] == "approved"
    assert payload["details"]["manual_confirmation"] is True
    assert payload["details"]["confirmed_action"] == "manual_deep_report"
    assert payload["details"]["generation_mode"] == "deterministic_template"
    assert payload["details"]["model_status"] == "not_used"
    assert "## 证据地图" in payload["body_markdown"]
    assert "## 审计边界" in payload["body_markdown"]
    assert "未调用模型" in payload["body_markdown"]
    assert "internal raw excerpt" not in payload["body_markdown"]
    for forbidden in ("买入", "卖出", "满仓", "稳赚", "保证收益"):
        assert forbidden not in payload["body_markdown"]

    assert list_response.status_code == 200
    assert [report["id"] for report in list_response.json()] == [report_id]
    assert other_user_response.status_code == 404


@pytest.mark.parametrize(
    "request_body",
    [
        {"signal_id": 1},
        {"signal_id": 1, "confirm_deep_report": False},
    ],
)
@pytest.mark.asyncio
async def test_report_api_rejects_manual_deep_report_without_confirmation(
    session_factory: async_sessionmaker[AsyncSession],
    client: AsyncClient,
    request_body: dict[str, object],
) -> None:
    signal_id = await _seed_signal(session_factory)
    body = {**request_body, "signal_id": signal_id}

    response = await client.post("/reports/deep/from-signal", json=body)
    list_response = await client.get("/reports")

    assert response.status_code == 400
    assert response.json()["detail"]["required_field"] == "confirm_deep_report"
    assert list_response.status_code == 200
    assert list_response.json() == []


@pytest.mark.asyncio
async def test_report_api_blocks_manual_deep_report_for_blocked_signal(
    session_factory: async_sessionmaker[AsyncSession],
    client: AsyncClient,
) -> None:
    signal_id = await _seed_signal(session_factory, evidence_count=1, with_evidence=False)

    response = await client.post(
        "/reports/deep/from-signal",
        json={"signal_id": signal_id, "confirm_deep_report": True},
    )
    list_response = await client.get("/reports")

    assert response.status_code == 409
    assert response.json()["detail"]["message"] == "signal review blocked report generation"
    assert "missing_evidence" in response.json()["detail"]["reasons"]
    assert list_response.status_code == 200
    assert list_response.json() == []


@pytest.mark.asyncio
async def test_report_api_marks_low_confidence_manual_deep_report_for_human_review(
    session_factory: async_sessionmaker[AsyncSession],
    client: AsyncClient,
) -> None:
    signal_id = await _seed_signal(session_factory, confidence=0.2)

    response = await client.post(
        "/reports/deep/from-signal",
        json={"signal_id": signal_id, "confirm_deep_report": True},
    )

    assert response.status_code == 201
    payload = response.json()
    assert payload["report_type"] == "deep"
    assert payload["status"] == "needs_human_review"
    assert payload["suggestion_label"] == "谨慎跟踪"
    assert "low_evidence_confidence" in payload["details"]["review_reasons"]


@pytest.mark.asyncio
async def test_report_api_marks_low_confidence_report_for_human_review(
    session_factory: async_sessionmaker[AsyncSession],
    client: AsyncClient,
) -> None:
    signal_id = await _seed_signal(session_factory, confidence=0.2)

    response = await client.post(
        "/reports/from-signal",
        params={"user_key": "telegram-1001"},
        json={"signal_id": signal_id, "report_type": "standard"},
    )
    list_response = await client.get(
        "/reports",
        params={"user_key": "telegram-1001", "report_type": "standard"},
    )

    assert response.status_code == 201
    payload = response.json()
    assert payload["report_type"] == "standard"
    assert payload["status"] == "needs_human_review"
    assert payload["suggestion_label"] == "谨慎跟踪"
    assert "low_evidence_confidence" in payload["details"]["review_reasons"]

    assert list_response.status_code == 200
    assert len(list_response.json()) == 1


@pytest.mark.asyncio
async def test_report_api_blocks_signal_without_evidence(
    session_factory: async_sessionmaker[AsyncSession],
    client: AsyncClient,
) -> None:
    signal_id = await _seed_signal(session_factory, evidence_count=1, with_evidence=False)

    response = await client.post(
        "/reports/from-signal",
        json={"signal_id": signal_id, "report_type": "quick"},
    )
    list_response = await client.get("/reports")

    assert response.status_code == 409
    assert response.json()["detail"]["message"] == "signal review blocked report generation"
    assert "missing_evidence" in response.json()["detail"]["reasons"]
    assert list_response.status_code == 200
    assert list_response.json() == []


@pytest.mark.asyncio
async def test_report_api_returns_404_for_missing_signal(client: AsyncClient) -> None:
    response = await client.post(
        "/reports/from-signal",
        json={"signal_id": 999999, "report_type": "quick"},
    )

    assert response.status_code == 404


@pytest.mark.asyncio
async def test_periodic_report_summarizes_signals_and_user_reports(
    session_factory: async_sessionmaker[AsyncSession],
    client: AsyncClient,
) -> None:
    signal_id = await _seed_signal(session_factory, priority="P0")
    await client.post(
        "/reports/from-signal",
        params={"user_key": "telegram-1001"},
        json={"signal_id": signal_id, "report_type": "standard"},
    )

    response = await client.get(
        "/reports/periodic",
        params={"user_key": "telegram-1001", "period": "daily"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["report_type"] == "daily"
    assert payload["user_key"] == "telegram-1001"
    assert payload["signal_count"] == 1
    assert payload["report_count"] == 1
    assert payload["push_count"] == 0
    assert payload["priority_counts"]["P0"] == 1
    assert payload["top_subjects"][0]["signal_id"] == signal_id
    assert "日报汇总" in payload["summary"]
    assert "BaizeFinDB 日报" in payload["body_markdown"]
    assert "internal raw excerpt" not in payload["body_markdown"]
    for forbidden in ("买入", "卖出", "满仓", "稳赚", "保证收益"):
        assert forbidden not in payload["body_markdown"]


@pytest.mark.asyncio
async def test_weekly_periodic_report_handles_empty_window(client: AsyncClient) -> None:
    response = await client.get(
        "/reports/periodic",
        params={"user_key": "telegram-1001", "period": "weekly"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["report_type"] == "weekly"
    assert payload["signal_count"] == 0
    assert payload["priority_counts"] == {"P0": 0, "P1": 0, "P2": 0}
    assert "暂无雷达信号" in payload["body_markdown"]


async def _seed_signal(
    session_factory: async_sessionmaker[AsyncSession],
    *,
    priority: str = "P1",
    confidence: float = 0.9,
    evidence_count: int = 1,
    with_evidence: bool = True,
) -> int:
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
            signal_key=f"test:report:{now.timestamp()}",
            subject_type="sector_concept",
            subject_code="GN001",
            subject_name="AI Applications",
            priority=priority,
            lifecycle_stage="developing",
            review_status="candidate",
            title="P1 radar candidate",
            summary="Research attention signal from provider data, without trading advice.",
            metrics={"pct_change": 3.2},
            evidence_count=evidence_count,
        )
        session.add(signal)
        await session.flush()

        if with_evidence:
            session.add(
                SignalEvidence(
                    signal_id=signal.id,
                    evidence_type="market_snapshot",
                    source_name="akshare",
                    source_ref="market_snapshot:1",
                    source_time=None,
                    collected_at=now,
                    raw_excerpt="internal raw excerpt",
                    normalized_summary="Provider snapshot summary.",
                    confidence=confidence,
                    freshness="snapshot_latest",
                    details={"source": "test"},
                    public_share_policy="internal_summary_only",
                ),
            )

        await session.commit()
        return signal.id
