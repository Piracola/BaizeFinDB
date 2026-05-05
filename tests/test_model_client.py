import asyncio
import json
import urllib.error
import urllib.request
from collections.abc import AsyncIterator
from pathlib import Path

import pytest
import pytest_asyncio
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.ai.model_client import (
    ModelCompletionRequest,
    ModelCompletionResponse,
    ModelHTTPResponse,
    ModelMessage,
    ModelProviderConfigError,
    ModelProviderHTTPError,
    ModelProviderTransportError,
    build_model_client,
    generate_model_completion_with_audit,
)
from app.core.config import Settings
from app.db.audit_models import ModelCallLog
from app.db.base import Base


class RecordingTransport:
    def __init__(self, outcomes: list[ModelHTTPResponse | Exception]) -> None:
        self.outcomes = outcomes
        self.calls: list[dict[str, object]] = []

    def __call__(
        self,
        request: urllib.request.Request,
        timeout: float,
    ) -> ModelHTTPResponse:
        self.calls.append(
            {
                "url": request.full_url,
                "headers": dict(request.header_items()),
                "body": json.loads((request.data or b"{}").decode("utf-8")),
                "timeout": timeout,
            },
        )
        outcome = self.outcomes.pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        return outcome


class FakeModelClient:
    def __init__(self, outcomes: list[ModelCompletionResponse | Exception]) -> None:
        self.outcomes = outcomes
        self.models: list[str] = []

    async def complete(
        self,
        request: ModelCompletionRequest,
        *,
        model: str,
    ) -> ModelCompletionResponse:
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


def _request() -> ModelCompletionRequest:
    return ModelCompletionRequest(
        call_site="radar.analysis.scaffold",
        messages=[
            ModelMessage(role="system", content="Return bounded analysis context."),
            ModelMessage(role="user", content="Explain a synthetic radar signal."),
        ],
        response_format={"type": "json_object"},
        timeout_seconds=7.5,
    )


def _enabled_settings(
    *,
    provider: str = "openai",
    fallback_model: str | None = None,
) -> Settings:
    kwargs = {
        "MODEL_ANALYSIS_ENABLED": True,
        "MODEL_PROVIDER": provider,
        "MODEL_PRIMARY_MODEL": "primary-model",
        "MODEL_FALLBACK_MODEL": fallback_model,
    }
    if provider == "openai":
        kwargs["OPENAI_API_KEY"] = "secret-openai-key"
    else:
        kwargs["MODEL_API_BASE_URL"] = "https://models.example.test/v1"
        kwargs["MODEL_API_KEY"] = "secret-custom-key"
    return Settings(**kwargs)


def test_openai_client_builds_chat_completions_request_and_parses_response() -> None:
    transport = RecordingTransport(
        [
            ModelHTTPResponse(
                status_code=200,
                body=json.dumps(
                    {
                        "model": "primary-model",
                        "choices": [{"message": {"content": "bounded answer"}}],
                    },
                ).encode("utf-8"),
            ),
        ],
    )
    client = build_model_client(_enabled_settings(provider="openai"), transport=transport)

    response = asyncio.run(client.complete(_request(), model="primary-model"))

    assert response.content == "bounded answer"
    assert response.model == "primary-model"
    assert response.provider == "openai"
    assert transport.calls[0]["url"] == "https://api.openai.com/v1/chat/completions"
    assert transport.calls[0]["timeout"] == 7.5
    headers = transport.calls[0]["headers"]
    assert headers["Authorization"] == "Bearer secret-openai-key"
    body = transport.calls[0]["body"]
    assert body["model"] == "primary-model"
    assert body["messages"] == [
        {"role": "system", "content": "Return bounded analysis context."},
        {"role": "user", "content": "Explain a synthetic radar signal."},
    ]
    assert body["response_format"] == {"type": "json_object"}


def test_custom_client_uses_configured_base_url_and_sanitizes_http_error() -> None:
    transport = RecordingTransport(
        [
            urllib.error.HTTPError(
                url="https://models.example.test/v1/chat/completions",
                code=429,
                msg="too many requests",
                hdrs=None,
                fp=None,
            ),
        ],
    )
    client = build_model_client(_enabled_settings(provider="custom"), transport=transport)

    with pytest.raises(ModelProviderHTTPError) as exc_info:
        asyncio.run(client.complete(_request(), model="primary-model"))

    assert transport.calls[0]["url"] == "https://models.example.test/v1/chat/completions"
    assert "secret-custom-key" not in str(exc_info.value)
    assert "Authorization" not in str(exc_info.value)
    assert "status 429" in str(exc_info.value)


def test_custom_client_rejects_embedded_base_url_credentials() -> None:
    settings = Settings(
        MODEL_ANALYSIS_ENABLED=True,
        MODEL_PROVIDER="custom",
        MODEL_PRIMARY_MODEL="primary-model",
        MODEL_API_BASE_URL="https://user:password@models.example.test/v1",
        MODEL_API_KEY="secret-custom-key",
    )

    with pytest.raises(ModelProviderConfigError) as exc_info:
        build_model_client(settings)

    assert "credentials" in str(exc_info.value)
    assert "user" not in str(exc_info.value)
    assert "password" not in str(exc_info.value)
    assert "secret-custom-key" not in str(exc_info.value)


@pytest.mark.asyncio
async def test_disabled_settings_return_disabled_without_network_or_audit(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    fake_client = FakeModelClient(
        [
            ModelCompletionResponse(
                content="should not be used",
                model="unused",
                provider="test",
            ),
        ],
    )
    async with session_factory() as session:
        result = await generate_model_completion_with_audit(
            session,
            _request(),
            settings=Settings(),
            client=fake_client,
        )
        log_count = await session.scalar(select(func.count(ModelCallLog.id)))

    assert result.status == "disabled"
    assert result.provider == "disabled"
    assert fake_client.models == []
    assert log_count == 0


@pytest.mark.asyncio
async def test_primary_success_returns_ok_without_audit_row(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    fake_client = FakeModelClient(
        [
            ModelCompletionResponse(
                content="primary response",
                model="primary-model",
                provider="openai",
            ),
        ],
    )

    async with session_factory() as session:
        result = await generate_model_completion_with_audit(
            session,
            _request(),
            settings=_enabled_settings(provider="openai"),
            client=fake_client,
        )
        log_count = await session.scalar(select(func.count(ModelCallLog.id)))

    assert result.status == "ok"
    assert result.content == "primary response"
    assert result.model == "primary-model"
    assert fake_client.models == ["primary-model"]
    assert log_count == 0


@pytest.mark.asyncio
async def test_primary_failure_fallback_success_writes_fallback_audit(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    fake_client = FakeModelClient(
        [
            ModelProviderHTTPError(429),
            ModelCompletionResponse(
                content="fallback response",
                model="fallback-model",
                provider="openai",
            ),
        ],
    )

    async with session_factory() as session:
        result = await generate_model_completion_with_audit(
            session,
            _request(),
            settings=_enabled_settings(provider="openai", fallback_model="fallback-model"),
            client=fake_client,
        )
        rows = (await session.scalars(select(ModelCallLog))).all()

    assert result.status == "fallback"
    assert result.content == "fallback response"
    assert result.model == "fallback-model"
    assert result.fallback_model == "fallback-model"
    assert result.audit_log_id == rows[0].id
    assert fake_client.models == ["primary-model", "fallback-model"]
    assert len(rows) == 1
    assert rows[0].status == "fallback"
    assert rows[0].primary_model == "primary-model"
    assert rows[0].fallback_model == "fallback-model"
    assert rows[0].raw_prompt is None
    assert rows[0].response_excerpt == "fallback response"
    assert rows[0].details["outcome"] == "fallback"
    assert rows[0].details["raw_prompt_saved"] is False


@pytest.mark.asyncio
async def test_primary_and_fallback_failure_writes_degraded_audit(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    fake_client = FakeModelClient(
        [
            ModelProviderHTTPError(500),
            ModelProviderTransportError("TimeoutError"),
        ],
    )

    async with session_factory() as session:
        result = await generate_model_completion_with_audit(
            session,
            _request(),
            settings=_enabled_settings(provider="custom", fallback_model="fallback-model"),
            client=fake_client,
        )
        rows = (await session.scalars(select(ModelCallLog))).all()

    assert result.status == "degraded"
    assert result.audit_log_id == rows[0].id
    assert fake_client.models == ["primary-model", "fallback-model"]
    assert len(rows) == 1
    assert rows[0].status == "degraded"
    assert rows[0].fallback_model is None
    assert rows[0].raw_prompt is None
    assert rows[0].details["fallback_attempted"] is True
    assert rows[0].details["fallback_error_type"] == "ModelProviderTransportError"


@pytest.mark.asyncio
async def test_malformed_provider_response_degrades_through_wrapper(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    transport = RecordingTransport(
        [
            ModelHTTPResponse(
                status_code=200,
                body=json.dumps({"choices": [{"message": {}}]}).encode("utf-8"),
            ),
        ],
    )
    client = build_model_client(_enabled_settings(provider="openai"), transport=transport)

    async with session_factory() as session:
        result = await generate_model_completion_with_audit(
            session,
            _request(),
            settings=_enabled_settings(provider="openai"),
            client=client,
        )
        row = await session.scalar(select(ModelCallLog))

    assert result.status == "degraded"
    assert result.error_type == "ModelProviderResponseError"
    assert row is not None
    assert row.status == "degraded"
    assert row.raw_prompt is None
    assert "secret-openai-key" not in (row.error_message or "")
    assert "Authorization" not in (row.error_message or "")


def test_model_client_module_does_not_depend_on_radar_or_delivery_layers() -> None:
    source = Path("backend/app/ai/model_client.py").read_text(encoding="utf-8")

    assert "app.radar" not in source
    assert "app.reports" not in source
    assert "app.telegram" not in source
    assert "app.providers" not in source
