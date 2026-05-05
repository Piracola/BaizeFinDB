import json
from collections.abc import AsyncIterator
from datetime import UTC, datetime

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.ai.model_client import (
    ModelCompletionRequest,
    ModelCompletionResponse,
    ModelProviderHTTPError,
)
from app.core.config import Settings
from app.db.audit_models import ModelCallLog
from app.db.base import Base
from app.db.radar_models import RadarScanBatch, RadarSignal, RadarSignalReview, SignalEvidence
from app.db.session import get_db_session
from app.main import create_app
from app.radar.service import (
    get_radar_signal_analysis,
    get_radar_signal_model_analysis_draft,
)


class FakeModelClient:
    def __init__(self, outcomes: list[ModelCompletionResponse | Exception]) -> None:
        self.outcomes = outcomes
        self.requests: list[ModelCompletionRequest] = []
        self.models: list[str] = []

    async def complete(
        self,
        request: ModelCompletionRequest,
        *,
        model: str,
    ) -> ModelCompletionResponse:
        self.requests.append(request)
        self.models.append(model)
        outcome = self.outcomes.pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        return outcome


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


def _enabled_settings(*, fallback_model: str | None = None) -> Settings:
    return Settings(
        MODEL_ANALYSIS_ENABLED=True,
        MODEL_PROVIDER="openai",
        MODEL_PRIMARY_MODEL="primary-model",
        MODEL_FALLBACK_MODEL=fallback_model,
        OPENAI_API_KEY="fake-openai-key",
    )


def _draft_payload(**overrides: object) -> str:
    payload = {
        "advisory_summary": "模型草稿摘要，参考 https://example.com/source。",
        "observations": ["板块扩散仍需观察。"],
        "risk_notes": ["证据质量仍需复核。"],
        "follow_up_questions": ["下一次扫描是否延续？"],
        "suggested_attention_label": "继续观察",
    }
    payload.update(overrides)
    return json.dumps(payload, ensure_ascii=False)


@pytest.mark.asyncio
async def test_model_analysis_draft_disabled_does_not_call_model_or_write_audit(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    fake_client = FakeModelClient(
        [ModelCompletionResponse(content=_draft_payload(), model="unused", provider="test")],
    )
    async with session_factory() as session:
        signal_id = await _analysis_signal(session)
        draft = await get_radar_signal_model_analysis_draft(
            session,
            signal_id,
            settings=Settings(),
            client=fake_client,
        )
        log_count = await session.scalar(select(func.count(ModelCallLog.id)))

    assert draft is not None
    assert draft.model_status == "disabled"
    assert draft.draft_status == "not_available"
    assert draft.advisory_summary == ""
    assert fake_client.requests == []
    assert log_count == 0


@pytest.mark.asyncio
async def test_model_analysis_draft_success_uses_sanitized_context_and_keeps_rules(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    fake_client = FakeModelClient(
        [
            ModelCompletionResponse(
                content=_draft_payload(),
                model="primary-model",
                provider="openai",
            ),
        ],
    )
    async with session_factory() as session:
        signal_id = await _analysis_signal(session)
        before = await get_radar_signal_analysis(session, signal_id)
        draft = await get_radar_signal_model_analysis_draft(
            session,
            signal_id,
            settings=_enabled_settings(),
            client=fake_client,
        )
        signal = await session.get(RadarSignal, signal_id)
        log_count = await session.scalar(select(func.count(ModelCallLog.id)))
        after = await get_radar_signal_analysis(session, signal_id)

    assert draft is not None
    assert draft.model_status == "ok"
    assert draft.draft_status == "ok"
    assert draft.model == "primary-model"
    assert draft.suggested_attention_label == "继续观察"
    assert draft.advisory_summary == "模型草稿摘要，参考 [source omitted]。"
    assert draft.audit_log_id is None
    assert log_count == 0
    assert signal is not None
    assert signal.priority == "P1"
    assert signal.lifecycle_stage == "developing"
    assert signal.review_status == "needs_human_review"
    assert before == after

    prompt_text = "\n".join(message.content for message in fake_client.requests[0].messages)
    assert "https://example.com" not in prompt_text
    assert "market.example.hk" not in prompt_text
    assert "raw_excerpt" not in prompt_text
    assert "source_ref" not in prompt_text


@pytest.mark.asyncio
async def test_model_analysis_draft_fallback_success_writes_fallback_audit(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    fake_client = FakeModelClient(
        [
            ModelProviderHTTPError(429),
            ModelCompletionResponse(
                content=_draft_payload(advisory_summary="fallback draft"),
                model="fallback-model",
                provider="openai",
            ),
        ],
    )
    async with session_factory() as session:
        signal_id = await _analysis_signal(session)
        draft = await get_radar_signal_model_analysis_draft(
            session,
            signal_id,
            settings=_enabled_settings(fallback_model="fallback-model"),
            client=fake_client,
        )
        rows = (await session.scalars(select(ModelCallLog))).all()

    assert draft is not None
    assert draft.model_status == "fallback"
    assert draft.draft_status == "ok"
    assert draft.model == "fallback-model"
    assert draft.fallback_model == "fallback-model"
    assert draft.audit_log_id == rows[0].id
    assert fake_client.models == ["primary-model", "fallback-model"]
    assert len(rows) == 1
    assert rows[0].status == "fallback"
    assert rows[0].raw_prompt is None


@pytest.mark.asyncio
async def test_model_analysis_draft_unsafe_output_blocks_and_audits(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    fake_client = FakeModelClient(
        [
            ModelCompletionResponse(
                content=_draft_payload(advisory_summary="建议马上买入并满仓。"),
                model="primary-model",
                provider="openai",
            ),
        ],
    )
    async with session_factory() as session:
        signal_id = await _analysis_signal(session)
        draft = await get_radar_signal_model_analysis_draft(
            session,
            signal_id,
            settings=_enabled_settings(),
            client=fake_client,
        )
        row = await session.scalar(select(ModelCallLog))

    assert draft is not None
    assert draft.model_status == "ok"
    assert draft.draft_status == "blocked"
    assert draft.advisory_summary == ""
    assert draft.blocked_terms == ["马上买入", "满仓"]
    assert row is not None
    assert draft.audit_log_id == row.id
    assert row.status == "degraded"
    assert row.raw_prompt is None
    assert row.details["draft_status"] == "blocked"


@pytest.mark.asyncio
async def test_model_analysis_draft_malformed_output_degrades_and_audits(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    fake_client = FakeModelClient(
        [
            ModelCompletionResponse(
                content="{bad json",
                model="primary-model",
                provider="openai",
            ),
        ],
    )
    async with session_factory() as session:
        signal_id = await _analysis_signal(session)
        draft = await get_radar_signal_model_analysis_draft(
            session,
            signal_id,
            settings=_enabled_settings(),
            client=fake_client,
        )
        row = await session.scalar(select(ModelCallLog))

    assert draft is not None
    assert draft.model_status == "ok"
    assert draft.draft_status == "degraded"
    assert row is not None
    assert row.status == "degraded"
    assert row.details["draft_status"] == "degraded"


@pytest.mark.asyncio
async def test_model_analysis_draft_api_defaults_disabled_and_returns_404(
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
            response = await client.post(f"/radar/signals/{signal_id}/model-analysis-draft")
            missing_response = await client.post("/radar/signals/999999/model-analysis-draft")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json()["model_status"] == "disabled"
    assert response.json()["draft_status"] == "not_available"
    assert "Manual opt-in model draft" in response.json()["boundary"]
    assert missing_response.status_code == 404


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
        signal_key=f"model-analysis:test:{now.timestamp()}",
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
