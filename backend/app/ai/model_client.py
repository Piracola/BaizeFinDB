"""OpenAI-compatible model client plus degradation audit wrapper."""

from __future__ import annotations

import asyncio
import json
import urllib.error
import urllib.request
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any, Literal, Protocol
from urllib.parse import urljoin, urlparse

from sqlalchemy.ext.asyncio import AsyncSession

from app.audit.model_audit import record_model_degradation
from app.core.config import Settings, get_settings

OPENAI_API_BASE_URL = "https://api.openai.com/v1"
CHAT_COMPLETIONS_PATH = "chat/completions"
DEFAULT_MODEL_REQUEST_TIMEOUT_SECONDS = 30.0
MAX_AUDIT_PROMPT_LENGTH = 12_000

ModelGenerationStatus = Literal["disabled", "ok", "fallback", "degraded"]


@dataclass(frozen=True)
class ModelMessage:
    role: str
    content: str


@dataclass(frozen=True)
class ModelCompletionRequest:
    call_site: str
    messages: Sequence[ModelMessage]
    response_format: dict[str, Any] | None = None
    timeout_seconds: float = DEFAULT_MODEL_REQUEST_TIMEOUT_SECONDS


@dataclass(frozen=True)
class ModelCompletionResponse:
    content: str
    model: str
    provider: str
    status_code: int | None = None


@dataclass(frozen=True)
class ModelGenerationResult:
    status: ModelGenerationStatus
    content: str | None = None
    model: str | None = None
    fallback_model: str | None = None
    provider: str | None = None
    audit_log_id: int | None = None
    error_type: str | None = None


@dataclass(frozen=True)
class ModelHTTPResponse:
    status_code: int
    body: bytes


class SyncHTTPTransport(Protocol):
    def __call__(
        self,
        request: urllib.request.Request,
        timeout: float,
    ) -> ModelHTTPResponse: ...


class ModelClient(Protocol):
    async def complete(
        self,
        request: ModelCompletionRequest,
        *,
        model: str,
    ) -> ModelCompletionResponse: ...


class ModelClientError(Exception):
    """Base class for sanitized model-client errors."""


class ModelProviderDisabledError(ModelClientError):
    def __init__(self) -> None:
        super().__init__("model provider is disabled")


class ModelProviderConfigError(ModelClientError):
    pass


class ModelProviderHTTPError(ModelClientError):
    def __init__(self, status_code: int) -> None:
        self.status_code = status_code
        super().__init__(f"model provider HTTP request failed with status {status_code}")


class ModelProviderTransportError(ModelClientError):
    def __init__(self, error_type: str) -> None:
        self.error_type = error_type
        super().__init__(f"model provider transport failed: {error_type}")


class ModelProviderResponseError(ModelClientError):
    pass


class DisabledModelClient:
    async def complete(
        self,
        request: ModelCompletionRequest,
        *,
        model: str,
    ) -> ModelCompletionResponse:
        raise ModelProviderDisabledError


class OpenAICompatibleModelClient:
    def __init__(
        self,
        *,
        provider: str,
        base_url: str,
        api_key: str,
        transport: SyncHTTPTransport | None = None,
    ) -> None:
        self.provider = provider
        self._base_url = base_url.strip().rstrip("/")
        self._api_key = api_key.strip()
        self._transport = transport or _urllib_transport

    async def complete(
        self,
        request: ModelCompletionRequest,
        *,
        model: str,
    ) -> ModelCompletionResponse:
        return await asyncio.to_thread(self._complete_sync, request, model.strip())

    def _complete_sync(
        self,
        request: ModelCompletionRequest,
        model: str,
    ) -> ModelCompletionResponse:
        _validate_completion_request(request, model)
        url = _join_api_path(self._base_url, CHAT_COMPLETIONS_PATH)
        http_request = urllib.request.Request(
            url=url,
            data=_completion_payload(request, model),
            headers={
                "Authorization": f"Bearer {self._api_key}",
                "Content-Type": "application/json",
            },
            method="POST",
        )

        try:
            response = self._transport(http_request, float(request.timeout_seconds))
        except urllib.error.HTTPError as exc:
            raise ModelProviderHTTPError(exc.code) from exc
        except Exception as exc:
            raise ModelProviderTransportError(exc.__class__.__name__) from exc

        return _parse_chat_completion_response(
            response,
            provider=self.provider,
            requested_model=model,
        )


async def generate_model_completion_with_audit(
    session: AsyncSession,
    request: ModelCompletionRequest,
    *,
    settings: Settings | None = None,
    client: ModelClient | None = None,
    commit: bool = True,
) -> ModelGenerationResult:
    current_settings = settings or get_settings()
    provider = current_settings.model_provider_normalized
    if not current_settings.model_analysis_enabled or provider == "disabled":
        return ModelGenerationResult(status="disabled", provider=provider)

    primary_model = _configured_value(current_settings.model_primary_model)
    if primary_model is None:
        error = ModelProviderConfigError("MODEL_PRIMARY_MODEL is required")
        return await _record_degraded_result(
            session,
            request,
            settings=current_settings,
            provider=provider,
            primary_model="unconfigured",
            error=error,
            details={"outcome": "degraded", "provider": provider, "configuration_error": True},
            commit=commit,
        )

    try:
        model_client = client or build_model_client(current_settings)
        response = await model_client.complete(request, model=primary_model)
        return ModelGenerationResult(
            status="ok",
            content=response.content,
            model=response.model,
            provider=response.provider,
        )
    except Exception as primary_error:
        return await _handle_primary_failure(
            session,
            request,
            settings=current_settings,
            provider=provider,
            primary_model=primary_model,
            client=client,
            primary_error=primary_error,
            commit=commit,
        )


def build_model_client(
    settings: Settings | None = None,
    *,
    transport: SyncHTTPTransport | None = None,
) -> ModelClient:
    current_settings = settings or get_settings()
    provider = current_settings.model_provider_normalized
    if not current_settings.model_analysis_enabled or provider == "disabled":
        return DisabledModelClient()

    if provider == "openai":
        api_key = _required_secret(
            current_settings.openai_api_key,
            "OPENAI_API_KEY is required for MODEL_PROVIDER=openai",
        )
        return OpenAICompatibleModelClient(
            provider=provider,
            base_url=OPENAI_API_BASE_URL,
            api_key=api_key,
            transport=transport,
        )

    if provider == "custom":
        api_key = _required_secret(
            current_settings.model_api_key,
            "MODEL_API_KEY is required for MODEL_PROVIDER=custom",
        )
        base_url = _required_config(
            current_settings.model_api_base_url,
            "MODEL_API_BASE_URL is required for MODEL_PROVIDER=custom",
        )
        _validate_custom_base_url(base_url)
        return OpenAICompatibleModelClient(
            provider=provider,
            base_url=base_url,
            api_key=api_key,
            transport=transport,
        )

    raise ModelProviderConfigError("MODEL_PROVIDER must be disabled, openai, or custom")


async def _handle_primary_failure(
    session: AsyncSession,
    request: ModelCompletionRequest,
    *,
    settings: Settings,
    provider: str,
    primary_model: str,
    client: ModelClient | None,
    primary_error: Exception,
    commit: bool,
) -> ModelGenerationResult:
    fallback_model = _configured_value(settings.model_fallback_model)
    model_client = client

    if fallback_model and fallback_model != primary_model:
        try:
            if model_client is None:
                model_client = build_model_client(settings)
            response = await model_client.complete(request, model=fallback_model)
        except Exception as fallback_error:
            return await _record_degraded_result(
                session,
                request,
                settings=settings,
                provider=provider,
                primary_model=primary_model,
                error=primary_error,
                details={
                    "outcome": "degraded",
                    "provider": provider,
                    "fallback_attempted": True,
                    "primary_error_type": primary_error.__class__.__name__,
                    "fallback_error_type": fallback_error.__class__.__name__,
                },
                commit=commit,
            )

        log = await record_model_degradation(
            session,
            call_site=request.call_site,
            primary_model=primary_model,
            fallback_model=fallback_model,
            prompt=_audit_prompt(request),
            error=primary_error,
            response_excerpt=response.content,
            details={
                "outcome": "fallback",
                "provider": provider,
                "fallback_attempted": True,
                "primary_error_type": primary_error.__class__.__name__,
            },
            settings=settings,
            commit=commit,
        )
        return ModelGenerationResult(
            status="fallback",
            content=response.content,
            model=response.model,
            fallback_model=fallback_model,
            provider=response.provider,
            audit_log_id=log.id,
            error_type=primary_error.__class__.__name__,
        )

    return await _record_degraded_result(
        session,
        request,
        settings=settings,
        provider=provider,
        primary_model=primary_model,
        error=primary_error,
        details={
            "outcome": "degraded",
            "provider": provider,
            "fallback_attempted": False,
            "fallback_skipped_reason": "not_configured_or_same_as_primary",
            "primary_error_type": primary_error.__class__.__name__,
        },
        commit=commit,
    )


async def _record_degraded_result(
    session: AsyncSession,
    request: ModelCompletionRequest,
    *,
    settings: Settings,
    provider: str,
    primary_model: str,
    error: Exception,
    details: dict[str, object],
    commit: bool,
) -> ModelGenerationResult:
    log = await record_model_degradation(
        session,
        call_site=request.call_site,
        primary_model=primary_model,
        prompt=_audit_prompt(request),
        error=error,
        details=details,
        settings=settings,
        commit=commit,
    )
    return ModelGenerationResult(
        status="degraded",
        provider=provider,
        model=primary_model,
        audit_log_id=log.id,
        error_type=error.__class__.__name__,
    )


def _urllib_transport(
    request: urllib.request.Request,
    timeout: float,
) -> ModelHTTPResponse:
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return ModelHTTPResponse(status_code=response.status, body=response.read())


def _completion_payload(request: ModelCompletionRequest, model: str) -> bytes:
    payload: dict[str, object] = {
        "model": model,
        "messages": [
            {
                "role": message.role,
                "content": message.content,
            }
            for message in request.messages
        ],
    }
    if request.response_format is not None:
        payload["response_format"] = request.response_format
    return json.dumps(payload, ensure_ascii=False).encode("utf-8")


def _parse_chat_completion_response(
    response: ModelHTTPResponse,
    *,
    provider: str,
    requested_model: str,
) -> ModelCompletionResponse:
    try:
        payload = json.loads(response.body.decode("utf-8")) if response.body else {}
    except json.JSONDecodeError as exc:
        raise ModelProviderResponseError("model provider response was not valid JSON") from exc

    try:
        message = payload["choices"][0]["message"]
        content = message["content"]
    except (KeyError, IndexError, TypeError) as exc:
        raise ModelProviderResponseError(
            "model provider response missing choices[0].message.content",
        ) from exc

    if not isinstance(content, str) or not content.strip():
        raise ModelProviderResponseError("model provider response content is empty")

    model = payload.get("model")
    return ModelCompletionResponse(
        content=content,
        model=model if isinstance(model, str) and model.strip() else requested_model,
        provider=provider,
        status_code=response.status_code,
    )


def _validate_completion_request(request: ModelCompletionRequest, model: str) -> None:
    if not model:
        raise ModelProviderConfigError("model name is required")
    if not request.call_site.strip():
        raise ModelProviderConfigError("call_site is required")
    if not request.messages:
        raise ModelProviderConfigError("at least one model message is required")
    if request.timeout_seconds <= 0:
        raise ModelProviderConfigError("timeout_seconds must be positive")
    for message in request.messages:
        if not message.role.strip():
            raise ModelProviderConfigError("message role is required")
        if not isinstance(message.content, str):
            raise ModelProviderConfigError("message content must be text")


def _audit_prompt(request: ModelCompletionRequest) -> str:
    prompt = "\n".join(f"{message.role}: {message.content}" for message in request.messages)
    if len(prompt) <= MAX_AUDIT_PROMPT_LENGTH:
        return prompt
    return f"{prompt[: MAX_AUDIT_PROMPT_LENGTH - 3]}..."


def _join_api_path(base_url: str, path: str) -> str:
    return urljoin(f"{base_url.strip().rstrip('/')}/", path)


def _configured_value(value: str | None) -> str | None:
    if value and value.strip():
        return value.strip()
    return None


def _required_config(value: str | None, message: str) -> str:
    configured = _configured_value(value)
    if configured is None:
        raise ModelProviderConfigError(message)
    return configured


def _required_secret(value: str | None, message: str) -> str:
    configured = _configured_value(value)
    if configured is None:
        raise ModelProviderConfigError(message)
    return configured


def _validate_custom_base_url(value: str) -> None:
    parsed = urlparse(value)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise ModelProviderConfigError("MODEL_API_BASE_URL must be an HTTP(S) URL with a host")
    try:
        _ = parsed.port
    except ValueError as exc:
        raise ModelProviderConfigError("MODEL_API_BASE_URL has an invalid port") from exc
    if parsed.username or parsed.password:
        raise ModelProviderConfigError("MODEL_API_BASE_URL must not embed credentials")
