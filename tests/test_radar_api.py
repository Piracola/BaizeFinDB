from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.db.base import Base
from app.db.provider_models import MarketSnapshot
from app.db.radar_models import RadarScanBatch, RadarSignal, RadarSignalReview, SignalEvidence
from app.db.session import get_db_session
from app.main import create_app
from app.radar.service import get_radar_signal_analysis


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
async def test_radar_api_runs_scan_and_reads_signals(
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
                        "pct_change": 3.4,
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

    app = create_app()

    async def override_db_session() -> AsyncIterator[AsyncSession]:
        async with session_factory() as session:
            yield session

    app.dependency_overrides[get_db_session] = override_db_session

    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            run_response = await client.post("/radar/scans/run")
            latest_response = await client.get("/radar/scans/latest")
            scan_id = run_response.json()["id"]
            scan_detail_response = await client.get(f"/radar/scans/{scan_id}")
            overview_response = await client.get("/radar/overview")
            signals_response = await client.get("/radar/signals", params={"priority": "P1"})
            signal_id = signals_response.json()[0]["id"]
            detail_response = await client.get(f"/radar/signals/{signal_id}")
            missing_scan_response = await client.get("/radar/scans/999999")
            missing_response = await client.get("/radar/signals/999999")
    finally:
        app.dependency_overrides.clear()

    assert run_response.status_code == 200
    assert run_response.json()["status"] == "success"
    assert run_response.json()["signals"][0]["priority"] == "P1"

    assert latest_response.status_code == 200
    assert latest_response.json()["summary"]["candidate_count"] == 1

    assert scan_detail_response.status_code == 200
    assert scan_detail_response.json()["id"] == run_response.json()["id"]

    assert overview_response.status_code == 200
    overview_payload = overview_response.json()
    assert overview_payload["latest_scan"]["id"] == run_response.json()["id"]
    assert overview_payload["priority_counts"] == {"P0": 0, "P1": 1, "P2": 0}
    assert overview_payload["lifecycle_counts"]["ignition"] == 1
    assert overview_payload["subject_count"] == 1
    assert overview_payload["current_subjects"][0]["subject_name"] == "AI Applications"
    backtrace = overview_payload["stock_backtrace_evidences"][0]
    assert backtrace["stock_name"] == "Example AI"
    assert backtrace["subject_name"] == "AI Applications"

    assert signals_response.status_code == 200
    assert signals_response.json()[0]["subject_name"] == "AI Applications"

    assert detail_response.status_code == 200
    assert detail_response.json()["evidences"][0]["evidence_type"] == "market_snapshot"

    assert missing_scan_response.status_code == 404
    assert missing_response.status_code == 404


@pytest.mark.asyncio
async def test_radar_signals_api_can_include_expired_p2(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    now = datetime.now(UTC)

    async with session_factory() as session:
        scan = RadarScanBatch(
            status="success",
            started_at=now,
            finished_at=now,
            source_snapshot_ids=[],
            summary={"priority_counts": {"P0": 0, "P1": 0, "P2": 2}},
        )
        session.add(scan)
        await session.flush()
        session.add_all(
            [
                _signal(
                    batch_id=scan.id,
                    signal_key="test:p2:api-expired",
                    subject_name="Expired P2 Theme",
                    created_at=now - timedelta(days=8),
                ),
                _signal(
                    batch_id=scan.id,
                    signal_key="test:p2:api-recent",
                    subject_name="Recent P2 Theme",
                    created_at=now - timedelta(days=1),
                ),
            ]
        )
        await session.commit()

    app = create_app()

    async def override_db_session() -> AsyncIterator[AsyncSession]:
        async with session_factory() as session:
            yield session

    app.dependency_overrides[get_db_session] = override_db_session

    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            default_response = await client.get(
                "/radar/signals",
                params={"priority": "P2"},
            )
            historical_response = await client.get(
                "/radar/signals",
                params={"priority": "P2", "include_expired_p2": True},
            )
    finally:
        app.dependency_overrides.clear()

    assert default_response.status_code == 200
    assert [signal["subject_name"] for signal in default_response.json()] == [
        "Recent P2 Theme"
    ]

    assert historical_response.status_code == 200
    assert {signal["subject_name"] for signal in historical_response.json()} == {
        "Expired P2 Theme",
        "Recent P2 Theme",
    }


@pytest.mark.asyncio
async def test_radar_signal_analysis_service_builds_safe_research_brief(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    async with session_factory() as session:
        signal_id = await _analysis_signal(session)

        analysis = await get_radar_signal_analysis(session, signal_id)

    assert analysis is not None
    assert analysis.signal_id == signal_id
    assert analysis.subject_name == "AI Applications"
    assert analysis.priority == "P1"
    assert analysis.lifecycle_stage == "developing"
    assert analysis.analysis_title == "P1 research brief: AI Applications"
    assert len(analysis.key_points) <= 5
    assert len(analysis.metric_highlights) <= 6
    assert "provider_quality_degraded" in analysis.risk_flags
    assert "low_evidence_confidence" in analysis.risk_flags
    assert analysis.evidence_summary.evidence_count == 1
    assert analysis.evidence_summary.summaries == [
        "Provider snapshot summary from [source omitted] with sector movement."
    ]
    assert analysis.evidence_summary.confidence_labels == ["low"]
    assert analysis.review_summary.status == "needs_human_review"
    assert analysis.review_summary.human_review_required is True
    assert "Do not override backend rule priority" in " ".join(
        analysis.agent_inputs.guardrails
    )
    assert [agent.agent_id for agent in analysis.agent_assessments] == [
        "data_quality_agent",
        "risk_agent",
        "momentum_agent",
        "evidence_agent",
        "report_agent",
    ]
    agent_by_id = {agent.agent_id: agent for agent in analysis.agent_assessments}
    assert agent_by_id["data_quality_agent"].status == "warning"
    assert agent_by_id["risk_agent"].status == "warning"
    assert agent_by_id["momentum_agent"].status == "warning"
    assert agent_by_id["evidence_agent"].status == "warning"
    assert agent_by_id["report_agent"].status == "warning"
    assert all(agent.summary for agent in analysis.agent_assessments)
    assert all(len(agent.findings) <= 5 for agent in analysis.agent_assessments)
    assert all(len(agent.next_actions) <= 5 for agent in analysis.agent_assessments)

    serialized = analysis.model_dump_json()
    assert "https://example.com" not in serialized
    assert "market.example.hk" not in serialized
    assert "source_ref" not in serialized
    assert "raw_excerpt" not in serialized
    assert "Raw source says" not in serialized
    assert '"confidence":' not in serialized
    assert "0.123" not in serialized
    assert "position_ratio" not in serialized
    assert "cost_price" not in serialized
    assert "buy" not in serialized.lower()
    assert "sell" not in serialized.lower()
    assert "买入" not in serialized
    assert "卖出" not in serialized


@pytest.mark.asyncio
async def test_radar_signal_analysis_api_reads_signal_and_returns_404(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    async with session_factory() as session:
        signal_id = await _analysis_signal(session)

    app = create_app()

    async def override_db_session() -> AsyncIterator[AsyncSession]:
        async with session_factory() as session:
            yield session

    app.dependency_overrides[get_db_session] = override_db_session

    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get(f"/radar/signals/{signal_id}/analysis")
            missing_response = await client.get("/radar/signals/999999/analysis")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    payload = response.json()
    assert payload["signal_id"] == signal_id
    assert payload["subject_name"] == "AI Applications"
    assert payload["analysis_title"] == "P1 research brief: AI Applications"
    assert payload["review_summary"]["status"] == "needs_human_review"
    assert [agent["agent_id"] for agent in payload["agent_assessments"]] == [
        "data_quality_agent",
        "risk_agent",
        "momentum_agent",
        "evidence_agent",
        "report_agent",
    ]
    assert {agent["status"] for agent in payload["agent_assessments"]} <= {
        "ok",
        "warning",
        "blocked",
        "not_applicable",
    }
    assert all(agent["summary"] for agent in payload["agent_assessments"])
    assert all(agent["findings"] for agent in payload["agent_assessments"])
    assert all(agent["next_actions"] for agent in payload["agent_assessments"])
    assert "https://example.com" not in response.text
    assert "market.example.hk" not in response.text
    assert "raw_excerpt" not in response.text
    assert '"confidence":' not in response.text
    assert missing_response.status_code == 404


def _signal(
    *,
    batch_id: int,
    signal_key: str,
    subject_name: str,
    created_at: datetime,
) -> RadarSignal:
    return RadarSignal(
        batch_id=batch_id,
        signal_key=signal_key,
        subject_type="sector_concept",
        subject_code=None,
        subject_name=subject_name,
        priority="P2",
        lifecycle_stage="developing",
        review_status="candidate",
        title=f"P2 radar candidate: {subject_name}",
        summary="Manual signal for API retention tests.",
        metrics={"pct_change": 1.2},
        evidence_count=0,
        created_at=created_at,
    )


async def _analysis_signal(session: AsyncSession) -> int:
    now = datetime.now(UTC)
    scan = RadarScanBatch(
        status="success",
        started_at=now,
        finished_at=now,
        source_snapshot_ids=[],
        summary={},
    )
    session.add(scan)
    await session.flush()

    signal = RadarSignal(
        batch_id=scan.id,
        signal_key=f"analysis:test:{now.timestamp()}",
        subject_type="sector_concept",
        subject_code="GN001",
        subject_name="AI Applications",
        priority="P1",
        lifecycle_stage="developing",
        review_status="needs_human_review",
        title="P1 radar candidate: AI Applications",
        summary="Research attention signal from provider data, no trading instruction.",
        metrics={
            "pct_change": 3.4,
            "breadth": 0.6923,
            "rising_count": 18,
            "falling_count": 8,
            "leading_stock": "Example AI",
            "leading_stock_pct_change": 7.5,
            "continuity": {"quick_report_candidate": True},
            "provider_quality": {
                "status": "degraded",
                "confidence": 0.123,
                "missing_fields": ["turnover_rate"],
            },
        },
        evidence_count=1,
        created_at=now,
    )
    session.add(signal)
    await session.flush()

    session.add(
        SignalEvidence(
            signal_id=signal.id,
            evidence_type="market_snapshot",
            source_name="market.example.hk",
            source_ref="https://example.com/raw/source",
            source_time=now,
            collected_at=now,
            raw_excerpt="Raw source says visit https://example.com/raw/source",
            normalized_summary=(
                "Provider snapshot summary from market.example.hk with sector movement."
            ),
            confidence=0.45,
            freshness="snapshot_latest",
            details={
                "source_url": "https://example.com/raw/source",
                "position_ratio": 0.2,
                "cost_price": 10.5,
            },
            public_share_policy="internal_summary_only",
        )
    )
    session.add(
        RadarSignalReview(
            signal_id=signal.id,
            review_status="needs_human_review",
            reviewer="test",
            rule_version="test",
            reasons=["low_evidence_confidence", "provider_quality_needs_review"],
            details={"min_evidence_confidence": 0.45},
        )
    )

    await session.commit()
    return signal.id
