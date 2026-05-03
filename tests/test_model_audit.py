from collections.abc import AsyncIterator

import pytest
import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.audit.model_audit import record_model_degradation
from app.db.audit_models import ModelCallLog
from app.db.base import Base


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
async def test_model_failure_degradation_records_hash_without_raw_prompt_by_default(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    prompt = "full prompt with private holding context"
    async with session_factory() as session:
        log = await record_model_degradation(
            session,
            call_site="reports.from_signal",
            primary_model="primary-model",
            prompt=prompt,
            error=TimeoutError("primary model timed out"),
        )
        stored_log = await session.scalar(select(ModelCallLog).where(ModelCallLog.id == log.id))

    assert stored_log is not None
    assert stored_log.status == "degraded"
    assert stored_log.primary_model == "primary-model"
    assert stored_log.fallback_model is None
    assert stored_log.error_type == "TimeoutError"
    assert stored_log.error_message == "primary model timed out"
    assert len(stored_log.prompt_hash) == 64
    assert stored_log.prompt_length == len(prompt)
    assert stored_log.raw_prompt is None
    assert stored_log.details["prompt_hash_version"] == "sha256:v1"
    assert stored_log.details["raw_prompt_saved"] is False


@pytest.mark.asyncio
async def test_model_fallback_record_can_store_raw_prompt_only_when_enabled(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    prompt = "debug prompt"
    async with session_factory() as session:
        log = await record_model_degradation(
            session,
            call_site="governance.review",
            primary_model="primary-model",
            fallback_model="fallback-model",
            prompt=prompt,
            error=RuntimeError("primary failed"),
            response_excerpt="fallback response",
            store_raw_prompt=True,
        )

    assert log.status == "fallback"
    assert log.fallback_model == "fallback-model"
    assert log.raw_prompt == prompt
    assert log.response_excerpt == "fallback response"
    assert log.details["raw_prompt_saved"] is True
